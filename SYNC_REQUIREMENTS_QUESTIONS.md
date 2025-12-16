# Salesforce → Pipedrive Sync: Requirements Questions

Please answer these questions to ensure the sync works exactly as you need it. I'll update the implementation based on your answers.

## 1. Salesforce Schema & Object Names

### 1.1 Loan Object
- **Q1.1**: What is the exact API name of your Loan object in Salesforce?
  - Is it `Loan__c`, `Opportunity`, or something else?
  - [Your answer: MtgPlanner_CRM__Transaction_Property__c]

### 1.2 Loan Officer Field
- **Q1.2**: What is the exact API name of the field that stores the Loan Officer?
  - [Your answer: Loan_Officer__c] it comes through as a data type of Text(255). Fair warning, I think the way that jungo does the sync is it pulls from encompass the "Loan Officer" in encompass to the Loan Officer field in jungo as a text field then uses the text field as a way to do a user lookup for the "Owner" field. The team uses the owner field to flip around owners but I think that's fine because I want to follow the true encompass data while is that "Loan_Officer__c" field that comes through as text.
  
- **Q1.3**: Is this field a:
  - [ ] Text field (stores "Jake Elmendorf" as text). The Loan_Officer__c field is Text(255) and comes through as "Jake Elmendorf"
  - [ ] Lookup field (references User object, stores User ID)
  - [ ] Other: _______________

- **Q1.4**: If it's a lookup, what is the relationship name? (e.g., `Loan_Officer__r`)
  - [Your answer: Like I mentioned before the text field comes from encompass and then the Owner field API name:OwnerId is the lookup field to the users. I dont care about this field.]

### 1.3 Primary Borrower Field
- **Q1.5**: What is the exact API name of the field that links to the Contact/borrower?
  - [Your answer: 	MtgPlanner_CRM__Borrower_Name__c] this is a datatype of Lookup(Contact)
  
- **Q1.6**: What is the relationship name for this lookup? (e.g., `Primary_Borrower__r`)
  - [Your answer: I'm not sure what you mean. The field name is Borrower_Name. The API name is 	MtgPlanner_CRM__Borrower_Name__c, the Object name it's under is "Loan", it is related to "Contact", API name is:	Contact]

### 1.4 Other Loan Fields
- **Q1.7**: What is the exact API name for the loan amount field?
  - [Your answer: there is 2 loan amount fields so for clarification the Loan Amount field that we're talking about in Pipedrive is in Jungo called Total Loan Amount. API name: Total_Loan_Amount__c]
  
- **Q1.8**: What is the exact API name for the loan stage/status field?
  - [Your answer: MtgPlanner_CRM__Status__c]. Something to note here, the field values are different.
  In Jungo the field values are (Values/API Name):
    Application / Application
    Pre-Approved / Pre-Approved
    GTR / Getting Things Rolling
    In Process / Loan In Process
    Submitted / Submitted
    Cond. Approval / Cond. Approval
    Approved / Approved
    Clear to Close / Clear to Close
    Docs Out / Docs Out
    Closed / Closed
    Suspended / Suspended
    Cancelled / Cancelled
So in Pipedrive I don't have that equivalent. My "Labels" are:
    Actively Searching
    Slowly Searching
    Scheduled Visit
    Waiting
    Urgent
    Making Offers
But the truth is, I never really ended up using the lables like this. I would much rather have my labels be exactly the same as how Jungo had it.
    Application means a file is brand new and I haven't been able to pre-approve it yet. (This would be in the pipeline stage Application In)
    Pre-Approved means I have pre-approved it (Pipeline stage Pre-Approved)
    GTR would be Getting things rolling and that would be pipeline stage Getting Things Rolling
    In Process, Submitted, Cond. Approval, Approved and Suspended would all mean the file is in process -- I would want the label to change according to how jungo shows it (this is from the encompass sync), but the pipeline stage in pipedrive would stay in the in the "Loan In Process" stage.
    Clear to close and Docs out would mean the file is cleared to close and the loan should be in pipeline stage Clear To Close
    Once the file is "Closed" this would mean the label in pipedrive gets updated to closed as well, runs the automation to mark as won status for the deal and run the other automation we have in place to update the "Person's" label as well.

  
- **Q1.9**: What is the exact API name for the close date/expected close date field?
  - [Your answer: MtgPlanner_CRM__Est_Closing_Date__c]

- **Q1.10**: Are there any other Loan fields you want to sync to Pipedrive? List them:
  - [Your answer: Yeah all of them... Everything I have in pipedrive I want synced pretty much except for the associations really.]
  Lets start with Loan fields since that's what this section is (Pipedrive name/API name in Jungo for the equivalent field) -- the names are almost exactly the same across jungo and pipedrive.
    Pre-Approval Sent Date / Pre_Approval_Sent__c
    Strategy Call / Strategy_Call__c
    Property Addresses. In Jungo they come through in seperated fields (address/city/state/postal code), in pipedrive it's all 1 field. So I would want to combine it into one properly formatted address and then import that into pipedrive.
        MtgPlanner_CRM__Property_Address__c
        MtgPlanner_CRM__Property_City__c
        MtgPlanner_CRM__Property_State__c
        MtgPlanner_CRM__Property_Postal_Code__c
    Property Type / 	MtgPlanner_CRM__Property_Type__c
    Loan Type / 	MtgPlanner_CRM__Loan_Type_1st_TD__c
    Loan Purpose / MtgPlanner_CRM__Loan_Purpose__c
    Occupancy / 	MtgPlanner_CRM__Occupancy__c
    Appraised Value / MtgPlanner_CRM__Appraised_Value__c
    Purchase Price / 	MtgPlanner_CRM__Purchase_Price__c
    Down Payment -- so for this one, encompass sends over a down payment $ amount. In pipedrive I have a %. I can just change this to a currency field or add a new one. Here is the API name: MtgPlanner_CRM__Down_Payment__c. Remind me that I need to create a Down Payment field that is a dollar amount not a percent.
    Base Loan Amount / MtgPlanner_CRM__Loan_Amount_1st_TD__c
    Loan Amount / Total_Loan_Amount__c
    Interest Rate / MtgPlanner_CRM__Rate_1st_TD__c -- something to note here. Data type in jungo is Percent(3, 3) and in pipedrive the field type is Numerical. I dont think they have a % field type.
    Term / MtgPlanner_CRM__Term_1st_TD__c
    Funding Fee / Funding_Fee__c -- Jungo data type is Text(255) and pipedrive is currency.. It definitely should be a currency.
    Credit Score / Middle_Credit_Score_Borrower__c
    Loan Program / MtgPlanner_CRM__Loan_Program_1st_TD__c
    Monthly Payment / MtgPlanner_CRM__Monthly_Payment_1st_TD__c
    P&I Payment  -- this isn't being pulled in correctly from encompass. remind me to go back and fix this sync.
    Homeowners Insurance / MtgPlanner_CRM__Hazard_Ins_1st_TD__c
    Property Tax / MtgPlanner_CRM__Property_Tax_1st_TD__c
    Mortgage Insurance / MtgPlanner_CRM__Mortgage_Ins_1st_TD__c
    HOA / MtgPlanner_CRM__HOA_1st_TD__c
    I dont have these following fields yet in Pipedrive but I want to make them: This would be under a section called "Important Dates"
        eConsent / eConsent__c
        LE Due / LE_Due__c
        LE Sent / LE_Sent__c
        LE Received / 	LE_Received__c
        Appraisal Ordered / Appraisal_Ordered__c
        Appraisal Received / Appraisal_Received__c
        Title Received / Title_Received__c
        Insurance Received / Insurance_Received__c
        CD Sent / CD_Sent__c
        CD Received / CD_Received__c
    Loan # / MtgPlanner_CRM__Loan_1st_TD__c
    Loan Paid Off / In_Process_or_Paid_Off__c
    I do not have the following fields created in pipedrive but I also need to create them:
        Salesforce ID -- I actually don't know how to find the API name for this. I can see the loan ID name in the URL but I don't know the API name for it. I could use the encompass GUID as a unique identifier to find that loan in jungo or better yet just the loan number? The loan number will always be a unique ID. I feel like the cleanest though would be the loan id.
        

## 2. Contact/Person Data

### 2.1 Contact Fields
- **Q2.1**: Do you want to sync ALL contact fields or just specific ones?
    So theoretically, I would have already created the person and the Lead in pipedrive before jungo ever sends me over anything. So in most cases, jungo should not be creating a contact. It will be updating an existing one. Let's match them up by the email as the unique Identifier. I will want to pull in "Name" which is API name of "Name" -- this is FirstName and LastName combined, then Email which is API name "Email" and Phone which is "Phone".

- **Q2.2**: Are there any Contact custom fields you want to sync to Pipedrive Person?
  - [Your answer: No] Most of what I do in pipedrive is out of leads/deals. Contacts really just houses the contact info. I only use a few other contact fields. Labels (which we already have automation set up for), and Contact Type -- this is either Client or Business in pipedrive. Clients are anybody that is a client that would do a loan with me. Business is anyone who is like a realtor or a builder or a title company rep.
  One thing I would want to have automation on, I don't know about a sync is in pipedrive my "Group" field, when I create a lead and an associated contact I add them to group "Lead". If a loan comes in from jungo, it more than likely won't be updating anything in the person because I already have the name, phone and email. (sometimes I have the name wrong, so we can always have the sync override the name I have in for the person), but once the update comes through, I want to drop the "Lead" tag under group and add "Borrower" I also need it to maintain any other group tag that was already there. -- WHEN WE GET TO THIS, we need to run tests for this one at a time to make sure it's executing correctly.
    I found a few more fields I want to sync that for some reason get put in the contact record in Jungo...
        Jungo Name: Income (Borrower), Jungo API: MtgPlanner_CRM__Income_Borrower__c. This needs to go to the DEAL in pipedrive, not the person. Right now I have B1 Annual Income, so I need to create a field in pipedrive for B1 Income and B2 Income and this will be their monthly figures so it can pull right from salesforce.
        Jungo Name: Income (Co Borrower), Jungo API: MtgPlanner_CRM__Income_Co_Borrower__c.
        Birthday = Birthdate
        Co Borrower's birthday is MtgPlanner_CRM__Birthdaycoborrower__c. BUT I won't have coborrower data living on the borrowers person in pipedrive. Coborrower's get their own person.

### 2.2 Multiple Borrowers
- **Q2.3**: Can a loan have multiple borrowers/contacts?
    Yes a loan can have 2 borrowers. Sometimes I create the person in pipedrive at the time of leads and sometimes I do not. Right now, the coborrower information will be sent to the contact record of the primary borrower in jungo. The fields are (jungo value/jungo API)
        Co Borrower First Name / 	MtgPlanner_CRM__Co_Borrower_First_Name__c
        Co Borrower Last Name / MtgPlanner_CRM__Co_Borrower_Last_Name__c -- Note I will need the name fields combined into one before sending into Pipedrive.
        Co Borrower Email / 	MtgPlanner_CRM__Co_Borrower_Email__c
        Co Borrower Phone / Phone_Co_Borrower__c
    Co Borrowers need to have their own Person in pipedrive and we need to associate this to the loan. There is a field in the loan in pipedrive called "CoBorrower Name" and this is an association to a person. I would need to have the coborrower data come right into here. Create a new coborrower person, if one doesn't already exist (using email as the unique id), and then after the person is created, associate them to the deal.


- **Q2.4**: If yes, should we:
    Per my previous note, the borrower contact should already have a person created in pipedrive 9 times out of 10 and it will be associated already. If it is not, then yes that will need to be associated. If there is a coborrower, we pull that coborrower data from jungo and create a new person in pipedrive (if one doesn't exist already) and then associate that to the deal under CoBorrower Name.

## 3. Field Mappings & Transformations

### 3.1 Stage Mapping
- **Q3.1**: What are the exact stage values in Salesforce? (List all possible values)
  - [Your answer: Answers provided as (values/api name)]
    Application / Application
    Pre-Approved / Pre-Approved
    GTR / Getting Things Rolling
    In Process / Loan In Process
    Submitted / Submitted
    Cond. Approval / Cond. Approval
    Approved / Approved
    Clear to Close / Clear to Close
    Docs Out / Docs Out
    Closed / Closed
    Suspended / Suspended
    Cancelled / Cancelled

- **Q3.2**: How should each Salesforce stage map to Pipedrive stages?
  - Example: "Application In" → Stage ID 123
  - [Your answer:     (Jungo Loan Status > Pipedrive Stage Name) I will create the "Labels" in the deal record on pipedrive to exactly match Jungo and we can update both the label and the pipedrive stage when a loan status change comes through.
    Application > Application In
    Pre-Approved / Pre-Approved
    GTR / Getting Things Rolling
    In Process / Loan In Process
    Submitted / Loan In Process
    Cond. Approval / Loan In Process
    Approved / Loan In Process
    Clear to Close / Clear To Close
    Docs Out / Clear To Close
    Closed / Clear To Close
    Suspended / Loan In Process
    Cancelled / Cancelled
    
    Note: Once Loan status Closed gets sent over, that means the deal status in pipedrive needs to be set to "won"
    NOTE - I DO NOT WANT CANCELLED COMING THROUGH FROM MY SYNC TO SET MY DEAL STATUS TO LOST OR ARCHIVE. I will do this manually. Essentially I dont want my team to accidentally archive something in my CRM and me not know about it.

- **Q3.3**: What should happen if a Salesforce status doesn't have a Pipedrive mapping?
    Everything should have a mapping.

### 3.2 Deal Title/Name
- **Q3.4**: What should the Pipedrive Deal title be?
    I want my deal name always to be in this format: [FirstName LastName - Loan # 123456789]
    Example: Jake Elmendorf - Loan # 5712495436.
    The name is pulled from the borrower name and the loan number is obviously pulled from the loan number coming in.

### 3.3 Amount/Value
- **Q3.5**: Should the loan amount sync to:
Good quesiton. So Jungo will be sending over "Loan Amount" which = "Base Loan Amount" in pipedrive and also "Total Loan Amount" which = "Loan Amount" and "Value" in pipedrive. So send that total loan amount field over to Both Loan Amount and Value in pipedrive.

### 3.4 Dates
- **Q3.6**: Should the close date sync to:
yes jungo's close date MtgPlanner_CRM__Est_Closing_Date__c would go to Expected Close Date (the native field) in pipedrive.

## 4. Sync Behavior & Edge Cases

### 4.1 New vs Existing Records
- **Q4.1**: When a loan is updated in Salesforce, should we:
    Contact data should never change, no need to keep syncing this after the original. Absolutely everything else is fair game. If an update is made in jungo, I would love to have that reflected in pipedrive in my corresponding deal.

- **Q4.2**: If a Person already exists in Pipedrive (by Salesforce Contact ID) but the name/email changed in Salesforce, should we:
    Interesting.. I can't find the API name for contactID in salesforce, but a name or email should never change. I would prefer to do that myself. Don't send it over to pipedrive.

### 4.2 Missing Data
- **Q4.3**: What should happen if a loan has no Primary Borrower/Contact?
    This is impossible, every deal in jungo has to have an associated borrower and contact record. Not to mention, before jungo ever syncs, 9 times out of 10, I've already created the lead and person so that association already exists. That case should never happen.

- **Q4.4**: What should happen if Contact has no Name?
    Use email as name. Again should never happen. The only time a jungo deal is being created is after someone fills out a loan application with all of their data, so I rarely will ever have incomplete or inaccurate data.

- **Q4.5**: What should happen if Loan Amount is null/zero?
    If for some reason loan amount is 0, which is should almost never be, then set it to 0, that's fine.

### 4.3 Deletions
- **Q4.6**: If a loan is deleted in Salesforce, should we:
    We typically do not delete deals ever in jungo, we mark as cancelled because it's reflective of a loan number in our encompass LOS. I don't ever want jungo marking status lost or archiving deals in pipedrive, i will do that manually.

- **Q4.7**: If a loan's Loan Officer changes (no longer "Jake Elmendorf"), should we:
    Good question. I think we should continue to sync that file. As long as I have a deal that still has a loan number that matches jungo or maybe I have the salesforce loanID in there, let's keep syncing it UNLESS I chose to archive or change deal status to lost.

### 4.4 Duplicates
- **Q4.8**: What if we find a Person in Pipedrive with the same email but different Salesforce Contact ID?
    Skip syncing. I don't want duplicates ever.

## 5. Sync Frequency & Performance

### 5.1 Polling Frequency
- **Q5.1**: How often should polling sync run?
    I don't really know if polling is the route I want to take, I think i want to just go based on updates from jungo, but whatever YOU think is easiest, I trust you. We can do every 15 minutes or 30 minutes. I'll tell you that in jungo, the sync updates every 15 minutes an essentially polls encompass to see if any changes were made to ANY of it's loans and makes updates accordingly to the loans that have changed. So every 15 minutes starting on the hour is how jungo syncs to encompass.

- **Q5.2**: For the initial sync, how many loans should we process at once?
    I don't want you to sync backwards, only forwards. This means only NEW loan creations after we start this. I already have all existing loan data in pipedrive.

### 5.2 Real-time Sync
- **Q5.3**: Do you want to set up Change Data Capture (real-time) now, or start with polling?
    I don't know... I trust you. I feel like CDC is going to be ALOT less queries. I might have a new deal created like 1-5 times a week and an update maybe like once or twice a day max? It wont be updating much. I feel like CDC is a lot more effective.

- **Q5.4**: If CDC, do you have access to set up Platform Events or webhooks in Salesforce?
    Pretend like I've never done this before, because I haven't but I have about 95% admin access in jungo. There's some things that the jungo platform itself has locked me out from doing but that's really just accessing their own managed packages. I should have access to do webhooks and APIs all myself.

## 6. Error Handling & Logging

### 6.1 Error Behavior
- **Q6.1**: If a single loan fails to sync, should we:
    Log error and try again? then maybe stop with just that one. I don't really know -- I trust your judgement.

- **Q6.2**: If Salesforce API is down/unavailable, should we:
  - [ ] Retry immediately
  - [ ] Wait and retry later
  - [ ] Send alert/notification
  - [ ] All of the above - This one.

### 6.2 Logging
- **Q6.3**: What level of logging do you want?
  - [ ] Minimal (errors only)
  - [ ] Normal (errors + important events) - Normal logging please. I would err on the side of more logging than less.
  - [ ] Verbose (everything, for debugging)

## 7. Custom Fields in Pipedrive

### 7.1 Existing Custom Fields
- **Q7.1**: Do you already have custom fields in Pipedrive that you want to populate from Salesforce?
  - List them: I already listed them under Q1.10. I know most of those fields, you don't have API keys for, so I'll have to update the api's in the .env.

- **Q7.2**: What Salesforce fields should map to which Pipedrive custom fields?
  - [Your answer: look under Q1.10]

### 7.2 New Custom Fields
- **Q7.3**: Should we create the "Salesforce Loan ID" and "Salesforce Contact ID" fields automatically, or will you create them?
    I'll create the fields in pipedrive and provide you the APIs in the .env and config file. For somet reason I can't find out how to find the ID's for loan id or contact id, but If you can figure it out, that's awesome.

## 8. Testing & Validation

### 8.1 Test Data
- **Q8.1**: Do you have a Salesforce sandbox/test environment we can use for testing?
  - [ ] Yes
  - [ ] No - will test in production (carefully) - This one.

- **Q8.2**: How many loans should we test with initially?
    Again, we won't test/import backwards. only new stuff. So I'll create a deal as a test deal and use this for our testing.

## 9. Future Considerations

### 9.1 Bidirectional Sync
- **Q9.1**: When you eventually want bidirectional sync, what Pipedrive data should go back to Salesforce?
  - [ ] Notes/Activities > Notes will go into a chatter post as my user and activities will go under chatter as my user as well.
  - [ ] Deal stage changes > Yes if I do update the deal stage we can send it back to jungo. The only time I will ever do this is if I am moving it into "getting things rolling", that's the only manual one.

### 9.2 Additional Features
- **Q9.2**: Are there any other features you want now or in the future?
  - [Your answer: No, lets just get this working.]

## 10. Your Specific Use Case

### 10.1 Workflow
- **Q10.1**: Walk me through your typical workflow:
  1. Loan is created in Salesforce/Jungo → What happens?
    I create a person and lead in pipedrive, I take notes in the lead. the lead has the associated person already. Client applies to my company for a loan and the loan pops up in encompass. Jungo reads encompass every 15 minutes. Jungo will then Create a contact and Loan simultaniuously because that contact will not exist already 9 times out of 10 in jungo (very small chance they already exist, in which case it would just associate the existing client), The loan will get created with stage Application in and all data that comes through from a clients app. From here I would like jungo to send this update to pipedrive and convert my lead to a deal and update all the data in from jungo and update the labels. From there, maintain the sync until the file goes into Closed and the status goes into status won - then we can stop pulling over data from that loan from jungo.
  2. Loan moves through stages → What should happen in Pipedrive?
    As the loan moves through the milestones in encompass, jungo gets updated and I want pipedrive to be updated as well.
  3. Loan closes → What should happen in Pipedrive?
    Loan closes and then the label needs to go to Closed and then the deal status goes to won and we can stop the sync. I wont need to pull any more data from jungo on that loan.
  4. Contact information changes → What should happen?
    Don't update, I'll do this manually. It's super rare contact information will ever change.

- **Q10.2**: Are there any specific business rules or edge cases I should know about?
  - [Your answer: I can't think of any right now, I was pretty thurough.]

---

Note for you:
Please provide me an action plan of everything I need to do for you. what fields I need to create in pipedrive, what API keys you need from me from pipedrive, im sure there's a lot, and then what API keys from salesforce, I should have provided you most of these. and then, I'll probably need to update the .env file myself will all of these API keys. and then obviously we need to set up the connection to salesforce and then somehow host this on render. I already have my render connected to my github.... That part is still a little hard for me to understand.
