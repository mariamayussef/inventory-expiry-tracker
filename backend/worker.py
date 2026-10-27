"""Idempotent in-app alert reconciliation. No email transport."""
import time, logging, os
from .db import connection,migrate
from .domain import refresh_alerts
logging.basicConfig(level=logging.INFO)
if __name__=='__main__':
    migrate()
    while True:
        try:
            with connection() as c: result=refresh_alerts(c)
            logging.info('Alert check successful: %s',result)
        except Exception: logging.exception('Alert check failed; retrying next interval')
        time.sleep(max(10,int(os.getenv('ALERT_INTERVAL_SECONDS','300'))))
