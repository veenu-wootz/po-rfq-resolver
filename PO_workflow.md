Purpose:
Ensure the PO is correct as per the Cost, Timeline, Scope and Quality promised durng quotation, Order Completion ownership is defined.

Steps:
1. Verify PO against Quotation Shared
2. Map PO to the Assemblies/Projects (May create new assemblies in the Project)
3. Review PO and the Projects/Assemblies


Tables:
1. Purchase Order

2. PO Projects
    2.1 Why does it has 10 rows, all are same except the 'Name' Column has 0 to 9 values and we have a 'Projects' Column that is a 'Single Value' Column Type (of Glide) and it extracts value from first row?
    This makes no sense for having 10 rows and then only selecting the first row. (Ask Vishal)
    -> It seems here to provide display options - Projects mapped to the PO.


Workflows:
1. User mails PO to 'po@wootz.work'
2. Mail Parser extarcts the text, attachments etc. and creates a row in Purchase Order Table
3. Verify PO against the Quotation
    3.1 Select the Projects involved in the PO
    3.2 Compare the PO against the Quotation
    3.3 Record PO info, Assign the Project


Flow and Screens:
1. Pending Verification (Table View)
2. Left Side: PO mail PDF Attachment, PO Mail
3. Right Side: Select Project -> Add, Below that shows a list of selected Project and then a button 'Verify PO'
4. 'Verify PO' Screen: Comparison Screen -> PO and Quotations
    4.1 Project Chips to change the Projects (based on the selected project)
    4.2 Each Project has a separate Quotation but all Quotation are compared against the same PO (as one PO can included order from different Project - we interanlly defined Project: One RFQ maps to one Project, but one PO can have orders related to multiple RFQs)
    4.3 Actions: Accept PO and Defer
5. Accept PO Screen: Input PO related Info - Won value (USD), PO#, PoC to define Assemblies, Remarks
6. Defer Screen: Input - Remarks

Workflows:

1. Add Project From PO
    1.1 Set 'Added To Projects' (to 'Project Name 2'), 'Added To Projects ID' ( to 'Lookup Project Row Id') in Purchase Order table
    1.2 Set 'Added RFQ Folder ID' (to 'Lookup RFQ Folder ID' in Purchase Order table)
    1.3 Set 'Purchase Order/Added PO ID' (to 'Lookup Added Project PO ID' in rel-Projects (relation with Table) )

2. Go to compare (Verify PO)
    1.1 Set Purchase Order
        1.1.1 'Purchase Orders/Project compare' Variable in 'User' Table, set it to 'Single project'of 'Purchase Order' table
    1.2 Set Link to screen in this item
        1.2.1 'Link to screen' Variable in 'Purchase Order' Table, set it to 'Link to current screen'


3. Send for Verification (Accept PO)
    1.1 Store PO related Values
    1.2 Send mails to related people - Accounts, Packaging & Delivery, POC etc.
    1.3 PowerAutomate Workflow
        1.3.1 Sends Google Attachments ID, RFQ FOlder ID and Row ID to powerautomate
        (Ask Vishal what it exactly does) -> Creates Attachments in related onedrive RFQ Folder
    1.4 PowerAutomae Workflow
        1.4.1 Sends Added To Projects ID
        (Ask Vishal what it exactly does) -> Turn on the visibility of the all Projects (requires flow as it is a list of project IDs)

4. Defer Purchase Order (Defer)
    2.1 Mark PO Deferred and record Deferral Reason






PO:
Pending Verification Workflow -> Mapping Workflow, Design, Build and Test
Intelligence Layer -> Integration

Quoted Workflow: 
Integrate it with AWS 'Quotation Database' Endpoint

Managing:
Quotation Database
CapMap Data transformation & Other Scripts
Website Scrapping Pipeline Review