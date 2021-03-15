import logging

import azure.functions as func
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    client_id = "ABNUyCiXJi38M8E4UGcZK1Rd7MrNLcSX9aRneVpRHdPNyD6K1B"
    client_secret = "k8OCVN3wwkhKvTga6xcM1W8HAff6HOx256g0Vzmg"
    redirect_uri = "https://sabstestfunc.azurewebsites.net/api/SABSAPP"
    local_redirect = "http://localhost:7071/api/SABSAPP"
    environment = "sandbox"

    # client_id = "ABk4eNRUFOjro5VRTLTo06IMl7JRejucH1pbu7ebjubGp5Ry5j"
    # client_secret = "OWLpShucAM9fVlG1tl0Awf2PslzxbbbctYRJkfLK"
    # redirect_uri = "https://sabstestfunc.azurewebsites.net/api/SABSAPP"
    # environment = "production"

    auth_client = AuthClient(
        client_id,
        client_secret,
        redirect_uri,
        environment
    )

    scopes = [
        Scopes.ACCOUNTING, Scopes.PAYMENT, Scopes.OPENID, Scopes. PROFILE,
        Scopes.EMAIL, Scopes.PHONE, Scopes. ADDRESS
    ]

    auth_url = auth_client.get_authorization_url(scopes)
    return func.HttpResponse(auth_url,status_code=200)
    