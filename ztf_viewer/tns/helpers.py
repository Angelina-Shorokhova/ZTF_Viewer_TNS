import io
import json
import time
import requests
import numpy as np
import pandas as pd
from astropy.table import Table

GROUP_ID = '95'
DATA_SOURCE_ID = '48'
ARCHIVE_ID = '2'
SNT = 3
MIN_POINTS = 2
CLRCOEFF_MAX = 0.2
SNAD_CACHE_DIR = '/tmp/snad_cache'
JSON_REPORTS_DIR = '/tmp/json_reports'
BOT_ID = '87994'
BOT_NAME = 'SNAD_bot'


def flux_error(mag, err_mag):
    err_down = 10**(-0.4*(mag - err_mag)) - 10**(-0.4*mag)
    err_up = 10**(-0.4*mag) - 10**(-0.4*(mag + err_mag))
    return 0.5*(err_down + err_up)


def mag_error(flux, err_flux):
    err_down = abs(-2.5*np.log10(flux + err_flux) + 2.5*np.log10(flux))
    err_up = abs(-2.5*np.log10(flux) + 2.5*np.log10(flux - err_flux))
    err_down = np.where(np.isnan(err_down), 1e4, err_down)
    err_up = np.where(np.isnan(err_up), 1e4, err_up)
    return err_down, err_up


def load_snad_data(oid, dr="dr24", cache_dir=SNAD_CACHE_DIR):
    import os
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'{oid}_{dr}.csv')
    if os.path.exists(cache_file):
        return Table.from_pandas(pd.read_csv(cache_file))
    url = f'https://ztf.snad.space/{dr}/csv/{oid}'
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=(30, 120))
            r.raise_for_status()
            with open(cache_file, 'w') as f:
                f.write(r.text)
            return Table.from_pandas(pd.read_csv(io.StringIO(r.text)))
        except requests.exceptions.Timeout:
            time.sleep(2 ** attempt * 2)
        except Exception:
            return None
    return None


def get_ra_dec(oid, cache_dir=SNAD_CACHE_DIR):
    import os
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'{oid}_coord.json')
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            d = json.load(f)
            return d['ra'], d['dec']
    url = f'http://db.ztf.snad.space/api/v3/data/latest/oid/full/json?oid={oid}'
    try:
        r = requests.get(url, timeout=(10, 60))
        soup = r.json()
        ra = round(soup[oid]['meta']['coord']['ra'], 5)
        dec = round(soup[oid]['meta']['coord']['dec'], 5)
        with open(cache_file, 'w') as f:
            json.dump({'ra': ra, 'dec': dec}, f)
        return ra, dec
    except Exception:
        return None, None


def enrich_data(data, ref, err_ref):
    data = data.copy()
    data['flux'] = 10**(-0.4*data['mag']) - 10**(-0.4*ref)
    data['fluxerr'] = np.sqrt(flux_error(data['mag'], data['magerr'])**2 +
                              flux_error(ref, err_ref)**2)
    data['magerr_down'] = mag_error(data['flux'], data['fluxerr'])[0]
    data['magerr_up'] = mag_error(data['flux'], data['fluxerr'])[1]
    return data


def find_first_detection(data, mjd_start):
    subset = data[data['mjd'] >= mjd_start]
    if len(subset) == 0:
        return None
    candidates = []
    for idx in range(len(subset)):
        row = subset[idx]
        if row['flux'] > SNT*row['fluxerr'] and abs(row.get('clrcoeff', 0)) < CLRCOEFF_MAX:
            candidates.append(idx)
        else:
            candidates = []
        if len(candidates) >= MIN_POINTS:
            row = subset[candidates[0]]
            return {
                'mjd': float(row['mjd']),
                'flux': float(row['flux']),
                'orig_mag': float(row['mag']),
                'magerr': float(row['magerr']),
                'magerr_down': round(float(row['magerr_down']), 2),
                'magerr_up': round(float(row['magerr_up']), 2),
                'filter': str(row['filter']),
            }
    return None


def build_remark(algorithm, obj_id, ztf_id, snad_name, custom_remark=""):
    if ztf_id and ztf_id.lower() != 'none':
        ztf_alert_remark = (f"The ZTF Alert ID for this object is {ztf_id}. "
                            f"The internal SNAD Object ID is {snad_name}.")
    else:
        ztf_alert_remark = (f"There is no ZTF Alert ID for this object (i.e., it is not present "
                            f"in the alert stream), so we report the internal SNAD Object ID instead. "
                            f"The internal SNAD Object ID is {snad_name}.")
    base = f"See more info at: https://ztf.snad.space/view/{obj_id}. {ztf_alert_remark}"
    if algorithm == 'AAD':
        return f"Transient was identified by AAD (https://arxiv.org/pdf/1909.13260.pdf). {base}"
    elif algorithm == 'PineForest':
        return f"Transient was identified by PineForest (https://arxiv.org/abs/2410.17142). {base}"
    elif algorithm == 'Miner':
        return f"Transient was identified by similarity search (https://arxiv.org/pdf/2111.11555.pdf). {base}"
    elif algorithm == 'Signature':
        return f"Transient was identified by signature similarity (https://arxiv.org/abs/2506.16314). {base}"
    elif algorithm == 'Custom':
        return custom_remark.strip() or base
    return f"{base}"


def build_phot_remark(ztf_id, ref, oid, passband):
    if ztf_id and ztf_id.lower() != 'none':
        return (f"For the first photometric point reference magnitude is {ref} mag. "
                f"ZTF DR OID {oid} ({passband}). ZTF Alert ID {ztf_id}.")
    return (f"For the first photometric point reference magnitude is {ref} mag. "
            f"ZTF DR OID {oid} ({passband}). No ZTF Alert ID found.")


def send_json_report(url, payload, api_key, bot_id, bot_name):
    try:
        headers = {'User-Agent': f'tns_marker{{"tns_id":{bot_id}, "type":"bot", "name":"{bot_name}"}}'}
        return requests.post(url + '/set/bulk-report', headers=headers,
                             data={'api_key': api_key, 'data': json.dumps(payload)},
                             timeout=(10, 60))
    except Exception as e:
        print(f"Send error: {e}")
        return None


def send_reply(url, report_id, api_key, bot_id, bot_name):
    try:
        headers = {'User-Agent': f'tns_marker{{"tns_id":{bot_id}, "type":"bot", "name":"{bot_name}"}}'}
        return requests.post(url + '/get/bulk-report-reply', headers=headers,
                             data={'api_key': api_key, 'report_id': report_id},
                             timeout=(10, 60))
    except Exception as e:
        print(f"Reply error: {e}")
        return None


def extract_objname(data):
    if isinstance(data, dict):
        if 'objname' in data:
            return data['objname']
        if 'new_object_name' in data:
            return data['new_object_name']
        for v in data.values():
            r = extract_objname(v)
            if r:
                return r
    elif isinstance(data, list):
        for item in data:
            r = extract_objname(item)
            if r:
                return r
    return None


def submit_report(url, payload, api_key, bot_id, bot_name):
    resp = send_json_report(url, payload, api_key, bot_id, bot_name)
    if resp is None:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if str(data.get('id_code')) != '200':
        return None
    report_id = str(data['data']['report_id'])
    for attempt in range(1, 6):
        time.sleep(5*attempt)
        rr = send_reply(url, report_id, api_key, bot_id, bot_name)
        if rr is None:
            continue
        if rr.status_code == 200:
            return extract_objname(rr.json())
        elif rr.status_code == 404:
            continue
    return None
