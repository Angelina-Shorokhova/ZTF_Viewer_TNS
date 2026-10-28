import os
import io
import re
import json
import time
import requests
import numpy as np
import pandas as pd
from astropy.table import Table
from astropy.coordinates import SkyCoord
from alerce.core import Alerce

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
    flux = np.clip(flux, 1e-10, None)
    err_down = abs(-2.5*np.log10(np.clip(flux + err_flux, 1e-10, None)) + 2.5*np.log10(flux))
    err_up = abs(-2.5*np.log10(flux) + 2.5*np.log10(np.clip(flux - err_flux, 1e-10, None)))
    err_down = np.where(np.isnan(err_down), 1e4, err_down)
    err_up = np.where(np.isnan(err_up), 1e4, err_up)
    return err_down, err_up

def load_snad_data(oid, dr="dr24", cache_dir=SNAD_CACHE_DIR):
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

def get_meta(oid, cache_dir=SNAD_CACHE_DIR):
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'{oid}_coord.json')
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                d = json.load(f)
                return d.get('ra'), d.get('dec'), d.get('ztf_id', 'None'), float(d.get('separation', 99.0))
        except Exception:
            pass
            
    url = f'http://db.ztf.snad.space/api/v3/data/latest/oid/full/json?oid={oid}'
    try:
        r = requests.get(url, timeout=(10, 60))
        soup = r.json()
        meta = soup[oid]['meta']
        ra = round(float(meta['coord']['ra']), 5)
        dec = round(float(meta['coord']['dec']), 5)
        
        ztf_id = 'None'
        separation = 99.0
        coord = SkyCoord(ra, dec, unit="deg")

        try:
            alerce = Alerce()
            df = alerce.query_objects(format="pandas", ra=ra, dec=dec, radius=2.0, page_size=128)
            if not df.empty:
                for _, row in df.iterrows():
                    if 'meanra' in row and 'meandec' in row:
                        c2 = SkyCoord(row['meanra'], row['meandec'], unit="deg")
                        sep = float(coord.separation(c2).arcsec)
                        if sep < separation:
                            separation = sep
                            ztf_id = str(row['oid'])
            print(f"DEBUG ALeRCE: Найден {ztf_id}, separation {separation}")
        except Exception as e:
            print(f"DEBUG ALeRCE: Ошибка - {e}")

        try:
            fink_url = "https://api.ztf.fink-portal.org/api/v1/conesearch"
            fink_payload = {"ra": ra, "dec": dec, "radius": 2.0}
            fink_resp = requests.post(fink_url, json=fink_payload, timeout=10)
            
            if fink_resp.status_code == 200:
                data = fink_resp.json()
                if isinstance(data, list) and len(data) > 0:
                    for obj in data:
                        if 'i:ra' in obj and 'i:dec' in obj and 'i:objectId' in obj:
                            c2 = SkyCoord(obj['i:ra'], obj['i:dec'], unit="deg")
                            sep = float(coord.separation(c2).arcsec)
                            if sep < separation:
                                separation = sep
                                ztf_id = obj['i:objectId']
            print(f"DEBUG Fink: Найден {ztf_id}, separation {separation}")
        except Exception as e:
            print(f"DEBUG Fink: Ошибка - {e}")

        print(f"DEBUG ИТОГ: ztf_id={ztf_id}, separation={separation}")

        with open(cache_file, 'w') as f:
            json.dump({'ra': ra, 'dec': dec, 'ztf_id': ztf_id, 'separation': separation}, f)
            
        return ra, dec, ztf_id, separation
    except Exception as e:
        print(f"Error in get_meta: {e}")
        return None, None, 'None', 99.0

def get_snad_name_from_catalog(oid, timeout=10):
    sheet_url = 'https://docs.google.com/spreadsheets/d/1sVgwCLy9i2kgDY1V7s1dy2nybCczL4hLq5mQ3txICNI/edit#gid=0'
    csv_export_url = sheet_url.replace('/edit#gid=', '/export?format=csv&gid=')
    
    try:
        response = requests.get(csv_export_url, timeout=timeout)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        
        match = df[df['OID'].astype(str) == str(oid)]
        if not match.empty:
            return str(match.iloc[-1]['Name'])
        
        if not df.empty and 'Name' in df.columns:
            last_name = str(df.iloc[-1]['Name'])
            num_match = re.search(r'(\d+)$', last_name)
            if num_match:
                next_num = int(num_match.group(1)) + 1
                prefix = last_name[:num_match.start(1)]
                return f"{prefix}{next_num}"
                
    except Exception as e:
        print(f"Warning: Could not fetch SNAD catalog: {e}")
        
    return f"SNAD{oid}"

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

def build_phot_remark(ztf_id, ref, oid, passband):
    if ztf_id and ztf_id.lower() != 'none':
        return (f"For the first photometric point reference magnitude is {ref} mag. "
                f"ZTF DR OID {oid} ({passband}). ZTF Alert ID is {ztf_id}.")
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

def build_payload(oid_dr, det, reporter, tns_type, remark, phot_remark):
    from astropy.time import Time
    t = Time(det['mjd'], format='mjd', scale='utc')
    discovery_datetime_str = t.iso

    filter_id = '110' if det['filter'] == 'zg' else '111'
    at_type = {'PSN': '1', 'PNV': '2', 'AGN': '3', 'NUC': '4', '0': '0'}.get(tns_type, '0')

    payload = {
        "at_report": {"0": {
            "ra":  {"value": str(oid_dr["ra"]), "units": "deg"},
            "dec": {"value": str(oid_dr["dec"]), "units": "deg"},
            "reporting_group_id": GROUP_ID,
            "discovery_data_source_id": DATA_SOURCE_ID,
            "reporter": f"{reporter} on behalf of the SNAD team",
            "discovery_datetime": discovery_datetime_str,
            "at_type": at_type,
            "internal_name": oid_dr["oid"],
            "internal_name_format": {"prefix": "", "year_format": "", "postfix": ""},
            "remarks": remark,
            "proprietary_period_groups": [GROUP_ID],
            "proprietary_period": {
                "proprietary_period_value": "0",
                "proprietary_period_units": "days",
            },
            "non_detection": {
                "obsdate": "", "limiting_flux": "", "flux_units": "",
                "filter_value": "", "instrument_value": "",
                "exptime": "", "observer": "", "comments": "",
                "archiveid": ARCHIVE_ID, "archival_remarks": "",
            },
            "photometry": {"photometry_group": {"0": {
                "obsdate": discovery_datetime_str,
                "flux": str(det['orig_mag']),
                "flux_error": "",
                "limiting_flux": "",
                "flux_units": "1",
                "filter_value": filter_id,
                "instrument_value": "196",
                "exptime": "",
                "observer": "ZTF",
                "comments": phot_remark,
            }}},
        }}
    }
    return payload

def update_snad_catalog(internal_snad_name, ra, dec, obj_id, discovery_date, mag, magerr_down, magerr_up, ref, err_ref, tns_name, tns_type, ztf_id="None"):
    try:
        catalog_entry_fn = f"{obj_id}_catalog_entry.csv"
        os.makedirs('./new_entry_for_SNAD_catalog_master', exist_ok=True)

        try:
            catalog_entry_df = pd.DataFrame([[f'{str(internal_snad_name)}', ra, dec, obj_id, str(discovery_date), f'{str(mag)}', magerr_down, magerr_up, ref, err_ref, f'AT {str(tns_name)}', tns_type, ztf_id, None, None, None]], 
                                            columns=['Name', 'R.A.', 'Dec.', 'OID', 'Discovery date (UT)', 'mag', 'er_down', 'er_up', 'ref', 'er_ref', 'TNS', 'Type', 'Comments', 'z_ph', 'er_z_ph', 'Remarks'])
        except Exception:
            catalog_entry_df = pd.DataFrame([[f'{str(internal_snad_name)}', ra, dec, obj_id, str(discovery_date), f'{str(mag)}', magerr_down, magerr_up, ref, err_ref, 'AT XXX', tns_type, ztf_id, None, None, None]], 
                                            columns=['Name', 'R.A.', 'Dec.', 'OID', 'Discovery date (UT)', 'mag', 'er_down', 'er_up', 'ref', 'er_ref', 'TNS', 'Type', 'Comments', 'z_ph', 'er_z_ph', 'Remarks'])
        
        catalog_entry_df.set_index('Name', inplace=True)
        catalog_entry_df.to_csv(f'./new_entry_for_SNAD_catalog_master/{catalog_entry_fn}', index=True)

        sheet_url = 'https://docs.google.com/spreadsheets/d/1sVgwCLy9i2kgDY1V7s1dy2nybCczL4hLq5mQ3txICNI/edit?gid=0#gid=0'
        csv_export_url = sheet_url.replace('/edit#gid=', '/export?format=csv&gid=')
        snad_catalog_df = pd.read_csv(csv_export_url, index_col=0)
        
        catalog_entry_df = pd.read_csv(f'./new_entry_for_SNAD_catalog_master/{catalog_entry_fn}', index_col=0)
        updated_snad_catalog_df = pd.concat([snad_catalog_df, catalog_entry_df])
        updated_snad_catalog_df.to_csv('SNAD_catalog_master_test.csv', index=True)
        return True
    except Exception as e:
        print(f"Error updating SNAD catalog: {e}")
        return False
