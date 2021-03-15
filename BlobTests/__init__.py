import logging
import json

import azure.functions as func


def main(req: func.HttpRequest, inputblob: func.InputStream, outputblob: func.Out[func.InputStream]) -> func.HttpResponse:

    auth_dataDict = {
    "realm_id": "",
    "access_token": "",
    "expires_in":0,
    "refresh_token":"",
    "x_refresh_token_expires_in": 0,
    "id_token": "",
    "date_created": 0
    }
    
    logging.info('Python HTTP trigger function processed a request.')
    bigbyte = inputblob.read()

    logging.info(type(bigbyte))
    k = bigbyte.decode()

    return func.HttpResponse(k,status_code=200)
