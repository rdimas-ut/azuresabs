import logging

import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(req.params)

    base_url = 'http://localhost:801/api/oauth/'
    header_file = dict()

    code = req.params.get("code")
    realmid = req.params.get("realmId")
    state = req.params.get("state")
    error = req.params.get("error")
    

    if not error:
         # send back correct reponse
        logging.info(code)
        logging.info(realmid)
        logging.info(state)
        logging.info(req.get_body())

        get_url = base_url + "?code=" + code + "&realmId=" + realmid + "&state=" + state

    else:
        # handle the error response
        logging.info(error)

        get_url = base_url + "?error=" + error

    
    logging.info(get_url)
    header_file.update({"Location": get_url})
    return func.HttpResponse(headers=header_file,status_code=303)
    

    

