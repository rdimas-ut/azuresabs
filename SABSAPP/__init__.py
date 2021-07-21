import logging
import azure.functions as func

import time
import json
import sqlite3
import tempfile

import pandas as pd
import datetime

from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.user_credential import UserCredential

from intuitlib.client import AuthClient
from intuitlib.exceptions import AuthClientError

from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer
from quickbooks.objects.vendor import Vendor
from quickbooks.objects.item import Item
from quickbooks.objects.account import Account

from quickbooks.objects.bill import Bill
from quickbooks.objects.detailline import AccountBasedExpenseLine, AccountBasedExpenseLineDetail

from quickbooks.objects.invoice import Invoice
from quickbooks.objects.detailline import SalesItemLine
from quickbooks.objects.detailline import SalesItemLineDetail

from quickbooks.objects.base import CustomerMemo

from time import strftime, localtime


defaultres = func.HttpResponse("This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",status_code=200)

# Start of qbo authentication
# client_id = "ABk4eNRUFOjro5VRTLTo06IMl7JRejucH1pbu7ebjubGp5Ry5j"
# client_secret = "OWLpShucAM9fVlG1tl0Awf2PslzxbbbctYRJkfLK"
# redirect_uri = "https://sabstestfunc.azurewebsites.net/api/SABSAPP"
# environment = "production"

# LOCAL
# local_redirect = "http://localhost:7071/api/SABSAPP"

# SABSTESFUNC
# redirect_uri = "https://sabstestfunc.azurewebsites.net/api/SABSAPP"

# SABSDEMO
redirect_uri = "https://sabsdemo.azurewebsites.net/api/SABSAPP"

# # SABSDEPONE
# redirect_uri = "https://sabsdepone.azurewebsites.net/api/SABSAPP"

# # Test App Production
# client_id = "ABk4eNRUFOjro5VRTLTo06IMl7JRejucH1pbu7ebjubGp5Ry5j"
# client_secret = "OWLpShucAM9fVlG1tl0Awf2PslzxbbbctYRJkfLK"
# environment = "production"

# Test App Development
client_id = "ABNUyCiXJi38M8E4UGcZK1Rd7MrNLcSX9aRneVpRHdPNyD6K1B"
client_secret = "k8OCVN3wwkhKvTga6xcM1W8HAff6HOx256g0Vzmg"
environment = "sandbox"




auth_client = AuthClient(
    client_id,
    client_secret,
    redirect_uri,
    environment,
)

isSignedInQBO = False

def main(req: func.HttpRequest, sharepointInputBlob: func.InputStream, sharepointOutputBlob: func.Out[func.InputStream], appStateInputBlob: func.InputStream, appStateOutputBlob: func.Out[func.InputStream], 
    qboAuthInputBlob: func.InputStream, qboAuthOutputBlob: func.Out[func.InputStream], 
    DBInputBlob: func.InputStream, DBOutputBlob: func.Out[func.InputStream]) -> func.HttpResponse:

    dispatcher = {"createBill": createBill, "refreshQBOData": refreshQBOData, "sharepoint": sharepoint,"createInvoice": createInvoice,"getState": getState, "insert": insert, "delete": delete, "execute": execute, "update":update, "refreshCustomer": refreshCustomer, "refreshVendor": refreshVendor, "revokeTokens": revokeTokens, "refreshItem": refreshItem, "refreshAccount": refreshAccount }
    
    global qboauth
    global appstate
    global sabsdb
    global sharepoint_cred

    # Initializes files
    sharepoint_cred = json.loads(sharepointInputBlob.read().decode())
    qboauth = json.loads(qboAuthInputBlob.read().decode())
    appstate = json.loads(appStateInputBlob.read().decode())
    sabsdb = tempfile.NamedTemporaryFile()
    with open(sabsdb.name, "wb") as f:
        f.write(DBInputBlob.read())
        f.close()

    # conn = sqlite3.connect(sabsdb.name)
    # conn.row_factory = sqlite3.Row
    # c = conn.cursor()
    # c.execute('select DispName from Customer')
    # r = [dict(row) for row in c.fetchall()]
    # print(r)

    initialize()
    logging.info('Python HTTP trigger function processed a request.')

    # For handlind redirect
    code = req.params.get("code")
    realmId = req.params.get("realmId")
    state = req.params.get("state")
    error = req.params.get("error")
    # For custom requests
    call = req.headers.get("call")
    if req.headers.get("parameters"):
        parameters = json.loads(req.headers.get("parameters"))

    # logging.info(call)
    # logging.info(parameters)
    # logging.info(type(parameters))

    if code and realmId and state:
        res = handleRedirect(code, realmId)
    elif error:
        logging.info(req.url)
        logging.info(req.files)
        res = func.HttpResponse("An error occured. Please look at azure portal for more info",status_code=500)
        logging.info(error)
    else:
        logging.info("handle customer requests")
        res = dispatcher[call](**parameters)


    # Writes out changes to files
    qboAuthOutputBlob.set(json.dumps(qboauth).encode())
    appStateOutputBlob.set(json.dumps(appstate).encode())
    with open(sabsdb.name, "rb") as f:
        DBOutputBlob.set(f.read())
        f.close()
    sabsdb.close()
    logging.info("Successfully wrote and read db")

    return res

# Handles sign out
def revokeTokens():
    global auth_client
    global qboauth
    global appstate
    auth_client.revoke()
    qboauth = {
    "realm_id": "",
    "access_token": "",
    "expires_in":0,
    "refresh_token":"",
    "x_refresh_token_expires_in": 0,
    "id_token": "",
    "date_created": 0
    }

    appstate = {
        "QBOisSignedIn": False 
    }
    
    return func.HttpResponse("Successful sign out", status_code=200)

# Refreshes customer table
def refreshCustomer():
    global sabsdb
    global isSignedInQBO

    logging.info('refrehsCustomer')

    if not isSignedInQBO:
        return func.HttpResponse("User is not signed in ot qbo", status_code=400)

    global client
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()
    c.execute('select * from Customer')
    current_customers = c.fetchall()
    logging.info(str(current_customers))
    conn.close()

    for cust in current_customers:
        delete('Customer', { 'DispName': cust[0]})
    
    customer_all = Customer.all(qb=client)
    new_customers = [str(i) for i in customer_all]

    for cust in new_customers:
        insert('Customer', {'DispName': cust})

    return func.HttpResponse("Successful refresh customers", status_code=200)

# Refreshes vendor table
def refreshVendor():
    global sabsdb
    global isSignedInQBO

    logging.info('refreshVendor')

    if not isSignedInQBO:
        return func.HttpResponse("User is not signed in ot qbo", status_code=400)

    global client
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()
    c.execute('select * from Vendor')
    current_vendors = c.fetchall()
    logging.info(str(current_vendors))
    conn.close()

    for ven in current_vendors:
        delete('Vendor', { 'DispName': ven[0]})
    
    vendor_all = Vendor.all(qb=client)
    new_vendor = [str(i) for i in vendor_all]

    for ven in new_vendor:
        insert('Vendor', {'DispName': ven})

    return func.HttpResponse("Successful refresh vendors", status_code=200)

# Refreshes item table
def refreshItem():
    global sabsdb
    global isSignedInQBO

    logging.info('refreshItem')

    if not isSignedInQBO:
        return func.HttpResponse("User is not signed in ot qbo", status_code=400)
    
    global client
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()
    c.execute('select * from Item')
    current_items = c.fetchall()
    logging.info(str(current_items))
    conn.close()

    for item in current_items:
        delete('Item', { 'Name': item[0]})

    item_all = Item.all(qb=client)
    new_item = [str(i) for i in item_all]

    for item in new_item:
        insert('Item', {'Name': item})

    return func.HttpResponse("Successful refresh items", status_code=200)

# Refrershes account table
def refreshAccount():
    global sabsdb
    global isSignedInQBO

    logging.info('refreshAccount')

    if not isSignedInQBO:
        return func.HttpResponse("User is not signed in ot qbo", status_code=400)
    
    global client
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()
    c.execute('select * from Account')
    current_accounts = c.fetchall()
    logging.info(str(current_accounts))
    conn.close()

    for account in current_accounts:
        delete('Account', { 'Name': account[0]})

    account_all = Account.all(qb=client)
    new_account = [str(i) for i in account_all]

    for account in new_account:
        insert('Account', {'Name': account})

    return func.HttpResponse("Successful refresh accounts", status_code=200)

# Refreshes QBO Data
def refreshQBOData():
    if isSignedInQBO:
        refreshAccount()
        refreshCustomer()
        refreshItem()
        refreshVendor()
        return func.HttpResponse("Successful refresh qbo data", status_code=200)
    else:
        return func.HttpResponse("QBO Data is not available", status_code=201)

# Creates the new invoice in QB and the SABS DB
def createInvoice(invData, invLines): 
    global isSignedInQBO


    # Takes the unix epoch time in ms to YYYY-MM-DD
    new_invoice_date = strftime("%Y-%m-01",localtime(int(invData.get("InvDate")/1000)))
    new_invoice_month = strftime("%b",localtime(int(invData.get("InvDate")/1000)))
    invoicememo = CustomerMemo()
    
    invoicememo.value = "Please note: \nPayments are due " + new_invoice_month + " 1st, but must be received no later than the " + new_invoice_month + " 15th or your stop loss insurance policy could lapse."

    if isSignedInQBO:
        global client
        customer = ""
        for cust in Customer.all(qb=client):
            if str(cust) == invData.get("Customer"):
                customer = cust
        
        if customer:
            invoice = Invoice()
            invoice.CustomerRef = customer.to_ref()
            invoice.BillEmail = customer.PrimaryEmailAddr
            invoice.DueDate = new_invoice_date
            invoice.CustomerMemo = invoicememo


            for li in invLines:
                line = SalesItemLine()
                line.Description = li.get('Description')
                line.Amount = li.get('Amount')
                line.SalesItemLineDetail = SalesItemLineDetail()
                line.SalesItemLineDetail.Qty = li.get('Qty')
                line.SalesItemLineDetail.UnitPrice = li.get('UnitPrice')
                line.SalesItemLineDetail.ServiceDate = None
                invoice.Line.append(line)      

            invoice.save(qb=client)
            query_invoice = Invoice.get(invoice.Id, qb=client) 

            inv_dict = {"IID": query_invoice.Id, "InvNum": invData.get("InvDate"), "Customer": invData.get("Customer"), "TotalDue": query_invoice.TotalAmt, "Balance": query_invoice.Balance}
            insert("Invoice", inv_dict)
        else:
            return func.HttpResponse("QBO not available. Please sign in again", status_code=201)
    else:
        return func.HttpResponse("QBO not available. Please sign in again", status_code=201)

    return func.HttpResponse("Successful create invoice", status_code=200)

# Creates the new Bill in QB and the SABS DB
def createBill(billData, billLines):
    global isSignedInQBO

    if isSignedInQBO:
        global client
        vendor = ""
        for ven in Vendor.all(qb=client):
            if str(ven) == billData.get("Vendor"):
                vendor = ven
        
        if vendor:
            bill = Bill()
            bill.VendorRef = vendor.to_ref()

            for li in billLines:
                line = AccountBasedExpenseLine()
                logging.info(li)
                line.Amount = li.get("Amount")
                line.Description = li.get('Description')
                line.DetailType = "AccountBasedExpenseLineDetail"
                line.AccountBasedExpenseLineDetail = AccountBasedExpenseLineDetail()

                account = False
                customer = False

                for act in Account.all(qb=client):
                    if str(act) == li.get("Category"):
                        account = True
                        line.AccountBasedExpenseLineDetail.AccountRef = act.to_ref()
                
                for cust in Customer.all(qb=client):
                    if str(cust) == li.get("Customer"):
                        customer = True
                        line.AccountBasedExpenseLineDetail.CustomerRef = cust.to_ref()

                logging.info(customer)
                logging.info(account)
                if account and customer:
                    logging.info("Successful line insert")
                    bill.Line.append(line)
        
            bill.save(qb=client)
            query_bill = Bill.get(bill.Id, qb=client)

            inv_dict = {"BID": query_bill.Id, "BillNum": billData.get("BillDate"), "Vendor": billData.get("Vendor"), "TotalDue": query_bill.TotalAmt, "Balance": query_bill.Balance}
            insert("Bill", inv_dict)
            logging.info(query_bill)
        else:
            return func.HttpResponse("QBO not available. Please sign in again", status_code=201)
    else:
        return func.HttpResponse("QBO not available. Please sign in again", status_code=201)

    return func.HttpResponse("Successful create invoice", status_code=200)

# Returns the json state
def getState():
    global qboauth
    qboauthjson = json.dumps(qboauth)    
    return  func.HttpResponse(qboauthjson, status_code=200)

# Insert a row by the dataDict spec
def insert(tableName, dataDict):
    global sabsdb
    logging.info(str(tableName))
    logging.info(str(dataDict))
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()

    commd = 'insert into ' + tableName + ' ('
    for key in dataDict.keys():
        commd += key + ', '
    commd = commd[0:-2] + ') values('

    values = ",".join(list(map(lambda key :'"' + dataDict.get(key) + '"' if isinstance(dataDict.get(key), str) else str(dataDict.get(key)), dataDict)))
    insert_commd = commd + values + ')'
    print(insert_commd)
    logging.info(insert_commd)
    c.execute(insert_commd)
    conn.commit()
    conn.close()

    return func.HttpResponse("Successful insert", status_code=200)

# Deletes a row by a single key value pair
def delete(tableName, searchDict):
    global sabsdb
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()
    
    commd = 'delete from ' + tableName + ' where '
    for key in searchDict:
        value = '"' + searchDict.get(key) + '"' if isinstance(searchDict.get(key), str) else str(searchDict.get(key))
        commd += key + ' = ' + value

    c.execute(commd)
    conn.commit()
    conn.close()
    return func.HttpResponse("Successful delete", status_code=200)

# Executes a single command and returns the result if applicable
def execute(commd):
    global sabsdb
    conn = sqlite3.connect(sabsdb.name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(commd)

    if 'select' in commd or 'SELECT' in commd:
        res_execute = [dict(row) for row in c.fetchall()]
        res_execute = {'res': list(res_execute)}
        result = json.dumps(res_execute)
        return func.HttpResponse(str(result), status_code=200)

    return func.HttpResponse("Successful execute", status_code=200)

# Updates a row in a table
def update(tableName, dataDict, searchDict):

    global sabsdb
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()
    
    commd = 'update ' + tableName + ' set '
    for key in dataDict:
        value = '"' + dataDict.get(key) + '"' if isinstance(dataDict.get(key), str) else str(dataDict.get(key))
        commd += key + ' = ' + value + ', '

    commd = commd[:-2] + ' where '
    for key in searchDict:
        value = '"' + searchDict.get(key) + '"' if isinstance(searchDict.get(key), str) else str(searchDict.get(key))
        commd += key + ' = ' + value

    c.execute(commd)
    conn.commit()
    conn.close()

    return func.HttpResponse("Successful update", status_code=200)

# Sharepoint csv exports
def sharepoint():
    global sabsdb
    global sharepoint_cred

    # Authoriziation by user credentials
    ctx = ClientContext(sharepoint_cred.get("site_url")).with_credentials(UserCredential(sharepoint_cred.get("username"), sharepoint_cred.get("password")))
    web = ctx.web
    ctx.load(web)
    ctx.execute_query()

    # Creates a temporary file and downloads the db contents to it
    fpcsv = tempfile.NamedTemporaryFile()

    # Creates sqlite connector
    conn = sqlite3.connect(sabsdb.name)
    c = conn.cursor()

    # Creates and uploads all of the tables from the db as csv files 
    target_folder = ctx.web.get_folder_by_server_relative_url(sharepoint_cred.get("csv_folder"))
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = c.fetchall()

    for table_name in tables:
        tname = table_name[0]
        table = pd.read_sql("SELECT * from %s" % tname, conn)
        

        if tname == "CensusLog":
            table["InvDate"] = table["InvDate"].apply(readable_time)
            table["CovDate"] = table["CovDate"].apply(readable_time)
            table["DTS"] = table["DTS"].apply(readable_time)

        if tname == "Policy":
            table["StartDate"] = table["StartDate"].apply(readable_time)
        
        table.to_csv(fpcsv.name, index=False)

        with open(fpcsv.name, 'rb') as content_file:
            file_content = content_file.read()
    
        target_file = target_folder.upload_file(tname + '.csv', file_content)
        ctx.execute_query()

    table = pd.read_sql("SELECT * from Census", conn)
    table["InvDate"] = table["InvDate"].apply(readable_time)
    table["CovDate"] = table["CovDate"].apply(readable_time)
    table.to_csv(fpcsv.name, index=False)

    with open(fpcsv.name, 'rb') as content_file:
        file_content = content_file.read()

    target_file = target_folder.upload_file("Census" + '.csv', file_content)
    ctx.execute_query()
    

    c.close()
    conn.close()
    fpcsv.close() 

    return func.HttpResponse(status_code=200)

# Handles sign in to qbo
def handleRedirect(code, realmId):
    global auth_client
    global qboauth
    global appstate

     # Gets access tokens for qbo
    auth_client.get_bearer_token(code, realm_id=realmId)

    qboauth = {
    "realm_id": auth_client.realm_id,
    "access_token": auth_client.access_token,
    "expires_in":auth_client.expires_in,
    "refresh_token":auth_client.refresh_token,
    "x_refresh_token_expires_in": auth_client.x_refresh_token_expires_in,
    "id_token": auth_client.id_token,
    "date_created": time.time()
    }

    appstate = {
        "QBOisSignedIn": True 
    }

    return func.HttpResponse("Authorization was succesful. You can close this window now.",status_code=200)

def refreshTokens(rf_token):
    global auth_client
    global qboauth
    global appstate
    global isSignedInQBO

    try: 
        auth_client.refresh(rf_token)
        qboauth = {
        "realm_id": auth_client.realm_id,
        "access_token": auth_client.access_token,
        "expires_in":auth_client.expires_in,
        "refresh_token":auth_client.refresh_token,
        "x_refresh_token_expires_in": auth_client.x_refresh_token_expires_in,
        "id_token": auth_client.id_token,
        "date_created": time.time()
        }

        appstate = {
            "QBOisSignedIn": True 
        }

        isSignedInQBO = True
    except AuthClientError:
        logging.info("An AuthClientError was raised.")
        qboauth = {
        "realm_id": "",
        "access_token": "",
        "expires_in":0,
        "refresh_token":"",
        "x_refresh_token_expires_in": 0,
        "id_token": "",
        "date_created": 0
        }

        appstate = {
            "QBOisSignedIn": False 
        }

        isSignedInQBO = False

    
    return None

def initialize():
    global qboauth
    global appstate
    global isSignedInQBO
    global auth_client

    expired_date = qboauth.get("expires_in") + qboauth.get("date_created")
    rf_expired_date = qboauth.get("x_refresh_token_expires_in") + qboauth.get("date_created")

    if qboauth.get("realm_id"):
        if expired_date > (time.time() + 100):
            auth_client.realm_id = qboauth.get("realm_id")
            auth_client.access_token = qboauth.get("access_token")
            auth_client.refresh_token = qboauth.get("refresh_token")
            isSignedInQBO = True
        elif expired_date < (time.time() + 100):
            if rf_expired_date > (time.time() + 100):
                auth_client.realm_id = qboauth.get("realm_id")
                refreshTokens(qboauth.get("refresh_token"))
            elif rf_expired_date < (time.time() + 100): 
                qboauth = {
                "realm_id": "",
                "access_token": "",
                "expires_in":0,
                "refresh_token":"",
                "x_refresh_token_expires_in": 0,
                "id_token": "",
                "date_created": 0
                }
                appstate = {"QBOisSignedIn": False}

    if isSignedInQBO:
        global client
        client = QuickBooks(
        auth_client=auth_client,
        company_id=qboauth.get("realm_id"),
        refresh_token=qboauth.get("refresh_token")
        )

    return None

def readable_time(timeValue):
    if isinstance(timeValue, str):
        return ""
    elif isinstance(timeValue, int) :
        if (len(str(timeValue)) > 10):
            return datetime.datetime.fromtimestamp(int(timeValue/1000))
        else:
            return datetime.datetime.fromtimestamp(timeValue)

    return ""