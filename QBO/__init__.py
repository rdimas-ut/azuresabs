import logging
import azure.functions as func

import time
import sqlite3
import tempfile
# import pandas as pd
import json

from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.user_credential import UserCredential
from intuitlib.client import AuthClient
from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer
from quickbooks.objects.vendor import Vendor

# Start of qbo authentication
client_id = "ABNUyCiXJi38M8E4UGcZK1Rd7MrNLcSX9aRneVpRHdPNyD6K1B"
client_secret = "k8OCVN3wwkhKvTga6xcM1W8HAff6HOx256g0Vzmg"
redirect_uri = "https://sabstestfunc.azurewebsites.net/api/QBO"
environment = "sandbox"
realm_id = 4620816365064521030

auth_client = AuthClient(
    client_id,
    client_secret,
    redirect_uri,
    environment,
    realm_id=realm_id
)



# Start of Sharepoint Persistent State/Hardcoded sharepoint credentials
site_url = 'https://aquilaanalytics.sharepoint.com/sites/SABenefitServices'
username = 'rcdimas@aquilabi.com'
password = 'L3tme!N9$'

# Authoriziation by user credentials
ctx = ClientContext(site_url).with_credentials(UserCredential(username, password))

# Filenames used in the sharepoint database
sabs_db = "sabs.db"
sabs_json = "sabsjson.json"
sabs_ejson = "sabsejson.json"

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    # logging.info(req.params)
    # logging.info(req.headers)
    # logging.info(req.get_body)

    code = req.params.get("code")
    realmId = req.params.get("realmId")
    state = req.params.get("state")
    error = req.params.get("error")

    if code and realmId and state:
        res = handleRedirect(code, realmId)
    elif error:
        res = func.HttpResponse("An error occured. Please look at azure portal for more info",status_code=500)
        logging.info(error)
    else:
        logging.info("We are in else")
        requestType = req.headers.get("RequestType")
        logging.info(requestType)
        if requestType == "refreshCustomer":
            res = refreshCustomer()
        elif requestType == "revokeTokens":
            res = revokeTokens()
        elif requestType == "refreshVendor":
            res = refreshVendor()
        elif requestType == "saveData":
            res = newwrite(req.headers.get("tableName"), req.headers.get("Data"), sabs_db)

    return res

def handleRedirect(code, realmId):
    # Gets access tokens for qbo
    auth_client.get_bearer_token(code, realm_id=realmId)
    auth_dataDict = {
    "realm_id": auth_client.realm_id,
    "access_token": auth_client.access_token,
    "expires_in":auth_client.expires_in,
    "refresh_token":auth_client.refresh_token,
    "x_refresh_token_expires_in": auth_client.x_refresh_token_expires_in,
    "id_token": auth_client.id_token,
    "date_created": time.time()
    }

    app_dataDict = {
        "QBOisSignedIn": True 
    }
    # Save them in a file in sharepoint
    write("JSON", auth_dataDict, sabs_ejson)
    write("JSON", app_dataDict, sabs_json)

    # Return an appropiate response
    return func.HttpResponse("Authorization was succesful. You can close this window now.",status_code=200)

def refreshTokens(rf_token):
    auth_client.refresh(rf_token)
    auth_dataDict = {
    "realm_id": auth_client.realm_id,
    "access_token": auth_client.access_token,
    "expires_in":auth_client.expires_in,
    "refresh_token":auth_client.refresh_token,
    "x_refresh_token_expires_in": auth_client.x_refresh_token_expires_in,
    "id_token": auth_client.id_token,
    "date_created": time.time()
    }

    app_dataDict = {
        "QBOisSignedIn": True 
    }
    # Save them in a file in sharepoint
    write("JSON", auth_dataDict, "sabsejson.json")
    write("JSON", app_dataDict, "sabsjson.json")

    return None

def revokeTokens():
    qbo()
    auth_client.revoke()
    auth_dataDict = {
    "realm_id": "",
    "access_token": "",
    "expires_in":0,
    "refresh_token":"",
    "x_refresh_token_expires_in": 0,
    "id_token": "",
    "date_created": 0
    }

    app_dataDict = {
        "QBOisSignedIn": False 
    }
    # Save them in a file in sharepoint
    write("JSON", auth_dataDict, "sabsejson.json")
    write("JSON", app_dataDict, "sabsjson.json")

    return func.HttpResponse(status_code=200)

def refreshCustomer():
    qbo()
    customer = Customer.all(qb=client)
    displayNames = [str(i) for i in customer]
    dataDict = {"DispName": displayNames}
    write("DB", dataDict, sabs_db, "Customer")

    return func.HttpResponse(status_code=200)

def refreshVendor():
    qbo()
    vendor = Vendor.all(qb=client)
    displayNames = [str(i) for i in vendor]
    dataDict = {"DispName": displayNames}
    write("DB", dataDict, sabs_db, "Vendor")

    return func.HttpResponse(status_code=200)

# Writes data to sharepoint. Modes include DB, and JSON.
def write(mode, dataDict, filename, tableName=None):
    app_folder = '/sites/SABenefitServices/Shared Documents/TestingForSharepoint/'
    filename_url = app_folder + filename

    # Handles JSON write for persistent states. Works by simply overwritting the contents
    if mode == "JSON":
        target_folder = ctx.web.get_folder_by_server_relative_url(app_folder)
        target_folder.upload_file(filename, dataDict)
        ctx.execute_query()
        logging.info(dataDict)
        return True

    # Creates a temporary file and downloads contents to it
    fp = tempfile.NamedTemporaryFile()
    try:
        ctx.web.get_file_by_server_relative_url(filename_url).download(fp).execute_query()
        if mode == "DB":
            # Handle DB writes to the sharepoint file
            conn = sqlite3.connect(fp.name)
            c = conn.cursor()
            c.execute('delete from ' + tableName)
            commd = 'insert into ' + tableName + ' ('
            for key in dataDict.keys():
                commd += key + ', '
            commd = commd[0:-2] + ') values('
            for i in range(len(dataDict.get(list(dataDict.keys())[0]))):
                sep = ","
                values = sep.join(list(map(lambda key :'"' + dataDict.get(key)[i] + '"' if isinstance(dataDict.get(key)[i], str) else str(dataDict.get(key)[i]), dataDict)))
                insert_commd = commd + values + ')'
                c.execute(insert_commd)
            conn.commit()
            conn.close()

            # Uploads the changed file
            with open(fp.name, "rb") as f:
                target_folder = ctx.web.get_folder_by_server_relative_url(app_folder)
                file_content = f.read()
                target_folder.upload_file(filename, file_content)
                ctx.execute_query()
            return True

    except Exception as e:
        logging.info(e.args)
        return False
    else:
        return False

# Reads data from json and returns the requested values
# IFU
def read(mode, filename):
    readDict = dict()
    app_folder = '/sites/SABenefitServices/Shared Documents/TestingForSharepoint/'
    file_loaded = False
    filename_url = app_folder + filename

    fp = tempfile.NamedTemporaryFile()
    try:
        with open(fp.name, "wb") as local_file:
            ctx.web.get_file_by_server_relative_url(filename_url).download(local_file).execute_query()
        file_loaded = True
    except Exception as e:
        logging.info(e.args)
    else:
        pass

    if file_loaded and mode == "JSON":
        with open(fp.name, 'r') as f:
            readDict = json.loads(f.read())
        fp.close() 
        return readDict
    elif file_loaded:
        return False
    else:
        return False

    return False

# Initializes values needed for qbo 
def qbo():
    qboClientState = read("JSON", sabs_ejson)
    
    expired_date = qboClientState.get("expires_in") + qboClientState.get("date_created")
    if expired_date < time.time():
        refreshTokens(qboClientState.get("refresh_token"))
    else:
        auth_client.access_token = qboClientState.get("access_token")
        auth_client.refresh_token = qboClientState.get("refresh_token")
    
    global client
    client = QuickBooks(
    auth_client=auth_client,
    company_id=realm_id,
    refresh_token=qboClientState.get("refresh_token")
    )

    return None

# Deletes table contents or a specific row
def newwrite(tableName, dataDict, filename):
    app_folder = '/sites/SABenefitServices/Shared Documents/TestingForSharepoint/'
    filename_url = app_folder + filename
    # Simple insert into table
    # Creates a temporary file and downloads contents to it
    fp = tempfile.NamedTemporaryFile()
    try:
        ctx.web.get_file_by_server_relative_url(filename_url).download(fp).execute_query()

        # Handle DB writes to the sharepoint file
        conn = sqlite3.connect(fp.name)
        c = conn.cursor()

        # Formats command
        commd = 'insert into ' + tableName + ' ('
        for key in dataDict.keys():
            commd += key + ', '
        commd = commd[0:-2] + ') values('

        values = ",".join(list(map(lambda key :'"' + dataDict.get(key) + '"' if isinstance(dataDict.get(key), str) else str(dataDict.get(key)), dataDict)))
        insert_commd = commd + values + ')'
        
        c.execute(insert_commd)
        conn.commit()
        conn.close()

        # Uploads the changed file
        with open(fp.name, "rb") as f:
            target_folder = ctx.web.get_folder_by_server_relative_url(app_folder)
            file_content = f.read()
            target_folder.upload_file(filename, file_content)
            ctx.execute_query()
            return func.HttpResponse(status_code=200)

    except Exception as e:
        logging.info(e.args)
        return False
    else:
        return False
