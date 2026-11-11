import numpy as np
import asyncio
import os
import json
import urllib.parse
import pandas as pd
from astropy.table import Table
from astropy.time import Time
from dash import Input, Output, State, callback, ctx, dcc, html, no_update

from ztf_viewer.tns import helpers
from ztf_viewer.tns.plot import build_lightcurve_figure
from ztf_viewer.catalogs.ztf_ref import ztf_ref
from ztf_viewer.akb import akb

TNS_TYPES = [
    {"label": "PSN - Possible SN", "value": "PSN"},
    {"label": "PNV - Possible Nova", "value": "PNV"},
    {"label": "AGN - Known AGN", "value": "AGN"},
    {"label": "NUC - Possibly nuclear", "value": "NUC"},
    {"label": "Other - Undefined", "value": "0"},
]

ALGORITHMS = [
    {"label": "AAD", "value": "AAD"},
    {"label": "PineForest", "value": "PineForest"},
    {"label": "Similarity Search (Miner)", "value": "Miner"},
    {"label": "Signature", "value": "Signature"},
    {"label": "Other", "value": "Custom"},
]

BTN_STYLE = {
    "display": "inline-flex",
    "alignItems": "center",
    "justifyContent": "center",
    "height": "40px",
    "padding": "0 20px",
    "boxSizing": "border-box",
    "border": "1px solid #888",
    "borderRadius": "4px",
    "textDecoration": "none",
    "color": "inherit",
    "cursor": "pointer",
    "fontSize": "14px",
    "fontWeight": "bold",
    "margin": "0 10px 0 0"
}

async def get_layout(pathname, search):
    params = {k: v[0] for k, v in urllib.parse.parse_qs(search.lstrip("?")).items()}
    oid = params.get("oid", "")
    dr = params.get("dr", "dr24")
    back_href = f"/{dr}/view/{oid}" if oid and dr else "/"

    default_reporter = "SNAD Reporter"
    try:
        default_reporter = await akb.username()
    except Exception as e:
        print(f"Auth error (user is probably not logged in): {e}")

    lc = None
    try:
        lc = await asyncio.to_thread(helpers.load_snad_data, oid, dr)
        if lc is not None:
            lc = lc[np.isfinite(lc['mjd']) & np.isfinite(lc['mag']) & np.isfinite(lc['magerr'])]
            if len(lc) == 0:
                lc = None
    except Exception as e:
        print(f"LC error: {e}")

    default_ref = "20.000"
    default_err = "0.100"
    try:
        ref_result = await ztf_ref.get(oid, dr)
        if not isinstance(ref_result, BaseException):
            default_ref = f"{(ref_result['mag'] + ref_result['magzp']):.3f}"
            default_err = f"{ref_result['sigmag']:.3f}"
    except Exception as e:
        print(f"Refmag error: {e}")

    if default_ref == "20.000" and lc is not None and len(lc) > 0:
        try:
            mags = sorted(lc['mag'])
            faintest_half = mags[len(mags)//2:]
            if faintest_half:
                val = float(np.median(faintest_half))
                if np.isfinite(val):
                    default_ref = f"{val:.3f}"
        except Exception as e:
            print(f"Fallback error: {e}")

    default_mjd_start = "58000"
    if lc is not None and len(lc) > 0:
        default_mjd_start = str(float(lc['mjd'].min()) - 10)
    
    ra, dec, ztf_id, separation = None, None, 'None', 99.0
    try:
        ra, dec, ztf_id, separation = await asyncio.to_thread(helpers.get_meta, oid)
    except Exception as e:
        print(f"Meta error: {e}")

    snad_name = f"SNAD_N"
    try:
        snad_name = await asyncio.to_thread(helpers.get_snad_name_from_catalog, oid)
        if not snad_name:
            snad_name = f"SNAD_N"
    except Exception as e:
        print(f"SnadName error: {e}")

    separation = float(separation) if separation is not None else 99.0
    ztf_id = str(ztf_id) if ztf_id is not None else 'None'
    default_internal_name = ztf_id if (ztf_id.lower() != 'none' and separation < 2) else snad_name

    if lc is None or len(lc) == 0:
        lc_json = {}
        lc_warning = html.P("Warning: Could not load light curve data from SNAD.", style={"color": "red"})
    else:
        lc_json = {
            "mjd": lc['mjd'].tolist(), "mag": lc['mag'].tolist(),
            "magerr": lc['magerr'].tolist(), "filter": lc['filter'].tolist(),
            "clrcoeff": (lc['clrcoeff'].tolist() if 'clrcoeff' in lc.colnames else [0.0]*len(lc)),
        }
        lc_warning = html.Div()

    return html.Div([
        dcc.Store(id="tns-lc-store", data=lc_json),
        dcc.Store(id="tns-oid-dr", data={
            "oid": oid, "dr": dr, "ra": ra, "dec": dec, 
            "ztf_id": ztf_id, "separation": separation, "snad_name": snad_name
        }),
        dcc.Store(id="tns-det-store"),

        html.Div([
            html.H2("Submit to TNS", style={"marginBottom": "5px"}),
            html.Div([
                html.Label("Submit Mode:", style={"fontWeight": "bold", "marginRight": "15px"}),
                dcc.RadioItems(
                    id="tns-mode",
                    options=[
                        {"label": "Sandbox", "value": "sandbox"},
                        {"label": "TNS", "value": "production"}
                    ],
                    value="sandbox",
                    inline=True,
                    labelStyle={"marginRight": "20px", "cursor": "pointer"}
                ),
            ], style={"marginBottom": "20px", "padding": "10px", "backgroundColor": "#e9ecef", "borderRadius": "5px"}),
            
            html.Div(id="tns-mode-warning", style={"color": "red", "fontWeight": "bold", "marginBottom": "20px"}),
            html.H4(f"Object OID: {oid} ({dr})", style={"color": "#666", "marginBottom": "20px"}),
            lc_warning,

            html.Div([
                html.Div([
                    html.Label("Reporter:", style={"fontWeight": "bold"}),
                    dcc.Input(id="tns-reporter", type="text", value=default_reporter, style={"width": "100%", "boxSizing": "border-box", "marginBottom": "15px"}),

                    html.Label("SNAD Name:", style={"fontWeight": "bold"}),
                    dcc.Input(id="tns-snad-name", type="text", value=snad_name, style={"width": "100%", "boxSizing": "border-box", "marginBottom": "15px"}),
                    
                    html.Label("Internal name:", style={"fontWeight": "bold"}),
                    dcc.Input(id="tns-internal-name", type="text", value=default_internal_name, style={"width": "100%", "boxSizing": "border-box", "marginBottom": "15px"}),                    
                    
                    html.Label("Method:", style={"fontWeight": "bold"}),
                    dcc.Dropdown(id="tns-method", options=ALGORITHMS, value="AAD", style={"marginBottom": "10px"}),
                    
                    html.Div([
                        dcc.Input(id="tns-method-other", type="text", placeholder="Method name", style={"width": "100%", "boxSizing": "border-box", "marginBottom": "5px"}),
                        dcc.Input(id="tns-method-article", type="text", placeholder="Article URL/Name (optional)", style={"width": "100%", "boxSizing": "border-box", "marginBottom": "15px"}),
                    ], id="custom-method-container", style={"display": "none"}),
                ], style={"flex": "1", "minWidth": "250px"}),

                html.Div([
                    html.Label("TNS Type:", style={"fontWeight": "bold"}),
                    dcc.Dropdown(id="tns-type", options=TNS_TYPES, value="PSN", style={"marginBottom": "15px"}),
                    
                    html.Label("Comment:", style={"fontWeight": "bold"}),
                    dcc.Textarea(id="tns-comment", style={"width": "100%", "boxSizing": "border-box", "height": "70px"}),
                ], style={"flex": "1", "minWidth": "250px"}),
            ], style={"display": "flex", "gap": "20px", "marginBottom": "20px", "backgroundColor": "#f8f9fa", "padding": "15px", "borderRadius": "8px"}),

            html.Label("Light Curve Parameters:", style={"fontWeight": "bold", "marginBottom": "10px"}),
            html.Div([
                html.Div([html.Label("Refmag:"), dcc.Input(id="tns-refmag", type="text", value=str(default_ref), style={"width": "100%", "boxSizing": "border-box", "color": "#000"})], style={"flex": "1"}),
                html.Div([html.Label("Err refmag:"), dcc.Input(id="tns-err-refmag", type="text", value=str(default_err), style={"width": "100%", "boxSizing": "border-box", "color": "#000"})], style={"flex": "1"}),
                html.Div([html.Label("MJD start:"), dcc.Input(id="tns-mjd-start", type="text", value=default_mjd_start, style={"width": "100%", "boxSizing": "border-box", "color": "#000"})], style={"flex": "1"}),
            ], style={"display": "flex", "gap": "20px", "marginBottom": "20px"}),

            dcc.Loading(dcc.Graph(id="tns-graph", config={'displayModeBar': True, 'displaylogo': False})),

            html.Div(id="tns-extracted", style={"marginTop": "15px", "fontFamily": "monospace", "fontSize": "18px", "backgroundColor": "#fff", "padding": "15px", "borderLeft": "5px solid #f1c40f", "boxShadow": "0 2px 5px rgba(0,0,0,0.1)"}),

            html.Label("Generated TNS Payload (Review):", style={"fontWeight": "bold", "marginTop": "25px"}),
            html.Pre(id="tns-generated-text", style={"whiteSpace": "pre-wrap", "border": "1px solid #ddd", "padding": "15px", "backgroundColor": "#fafafa", "fontSize": "12px", "marginBottom": "20px", "maxHeight": "300px", "overflowY": "scroll"}),

            html.Div([
                dcc.Link("BACK TO OBJECT", href=back_href, style=BTN_STYLE),
                html.Button("SUBMIT REPORT", id="tns-submit-button", n_clicks=0, style=BTN_STYLE),
                html.Button("FORCE SUBMIT", id="tns-force-submit-btn", n_clicks=0, 
                            style={**BTN_STYLE, "backgroundColor": "#f0ad4e", "display": "none"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "30px"}),

            dcc.Loading(html.Div(id="tns-submit-output", style={"fontSize": "16px", "fontWeight": "bold"})),
            
        ], style={"maxWidth": "900px", "margin": "0 auto"})
    ], style={"padding": "20px"})

@callback(
    Output("custom-method-container", "style"),
    Input("tns-method", "value")
)
def toggle_method_other(method):
    return {"display": "block", "width": "100%"} if method == "Custom" else {"display": "none"}

@callback(
    Output("tns-graph", "figure"), Output("tns-extracted", "children"), Output("tns-det-store", "data"),
    Input("tns-refmag", "value"), Input("tns-err-refmag", "value"), Input("tns-mjd-start", "value"),
    State("tns-lc-store", "data"),
)
def update_plot(ref_str, err_ref_str, mjd_start_str, lc_json):
    try:
        ref = float(ref_str)
        err_ref = float(err_ref_str)
        mjd_start = float(mjd_start_str)
    except (ValueError, TypeError):
        return no_update, "Invalid numeric values.", None

    if not lc_json:
        return no_update, no_update, no_update
        
    lc = Table.from_pandas(pd.DataFrame(lc_json))
    enriched = helpers.enrich_data(lc, ref, err_ref)
    
    det = helpers.find_first_detection(enriched, mjd_start)    
    
    if det is None:
        return no_update, "No detection found. Adjust refmag or MJD start.", None
        
    fig = build_lightcurve_figure(enriched, det)
    t = Time(det['mjd'], format='mjd', scale='utc')
    
    extracted = html.Div([
        html.Div([html.B("Discovery date (UT): "), t.iso]),
        html.Div([html.B("MJD: "), f"{det['mjd']:.5f}"]),
        html.Div([html.B("Magnitude: "), f"{det['orig_mag']:.2f} ± {det['magerr']:.2f}"]),
        html.Div([html.B("Filter: "), det['filter']]),
    ])
    return fig, extracted, det

def get_remark_text(method, method_other, method_article, comment, oid_dr, internal_name, snad_name):
    is_ztf = internal_name.strip().upper().startswith("ZTF")
    
    if is_ztf:
        ztf_alert_remark = f"The ZTF Alert ID for this object is {internal_name}. The internal SNAD Object ID is {snad_name}."
    else:
        ztf_alert_remark = f"There is no ZTF Alert ID for this object. The internal SNAD Object ID is {snad_name}."

    base_remark = f"See more info at: https://ztf.snad.space/view/{oid_dr['oid']}. {ztf_alert_remark}"

    algorithm = method_other if method == "Custom" else method
    custom_method_text = (method_other or "").strip()

    if method == "Custom" and custom_method_text:
        article_text = f" ({method_article})" if method_article else ""
        remark = f"Transient was identified by {custom_method_text}{article_text}.\n{base_remark}"
    else:
        if algorithm == 'AAD':
            remark = f"Transient was identified by AAD (https://arxiv.org/pdf/1909.13260.pdf). {base_remark}"
        elif algorithm == 'PineForest':
            remark = f"Transient was identified by PineForest (https://arxiv.org/abs/2410.17142). {base_remark}"
        elif algorithm == 'Miner':
            remark = f"Transient was identified by similarity search (https://arxiv.org/pdf/2111.11555.pdf). {base_remark}"
        elif algorithm == 'Signature':
            remark = f"Transient was identified by signature similarity (https://arxiv.org/abs/2506.16314). {base_remark}"
        else:
            remark = f"Transient identified by machine learning algorithms. {base_remark}"

    if comment and comment.strip():
        remark = f"{comment.strip()} {remark}"
        
    return remark

@callback(
    Output("tns-generated-text", "children"),
    Input("tns-method", "value"), Input("tns-method-other", "value"), Input("tns-method-article", "value"),
    Input("tns-comment", "value"), Input("tns-reporter", "value"), Input("tns-type", "value"), Input("tns-refmag", "value"),
    Input("tns-det-store", "data"), Input("tns-snad-name", "value"), Input("tns-internal-name", "value"),
    State("tns-oid-dr", "data"),
)
def update_generated_text(method, method_other, method_article, comment, reporter, tns_type, ref_str, det, snad_name, internal_name, oid_dr):
    if not oid_dr or not snad_name or not internal_name:
        return "Loading data..."
   
    if not det:
        return "No detection found. Please adjust the Refmag value."
    t = Time(det['mjd'], format='mjd', scale='utc')
    discovery_datetime_str = t.iso
    internal_name = helpers.validate_internal_name(internal_name, snad_name, discovery_datetime_str, oid_dr.get("ztf_id", "None"))

    remark = get_remark_text(method, method_other, method_article, comment, oid_dr, internal_name, snad_name)
    phot_remark = helpers.build_phot_remark(internal_name, ref_str, oid_dr["oid"], det["filter"]) 
    
    payload = helpers.build_payload(oid_dr, det, reporter, tns_type, remark, phot_remark)
    payload["at_report"]["0"]["internal_name"] = internal_name
    payload["at_report"]["0"]["photometry"]["photometry_group"]["0"]["flux"] = str(round(det['orig_mag'], 2))
    
    return json.dumps(payload, indent=4)

@callback(
    Output("tns-submit-output", "children"),
    Output("tns-force-submit-btn", "style"),
    Input("tns-submit-button", "n_clicks"),
    Input("tns-force-submit-btn", "n_clicks"),
    State("tns-det-store", "data"), State("tns-oid-dr", "data"), State("tns-refmag", "value"),
    State("tns-err-refmag", "value"),
    State("tns-reporter", "value"), State("tns-method", "value"), State("tns-method-other", "value"),
    State("tns-method-article", "value"), State("tns-comment", "value"), State("tns-type", "value"),
    State("tns-snad-name", "value"), State("tns-internal-name", "value"),
    State("tns-mode", "value"),
    prevent_initial_call=True,
)
async def handle_submit(n_clicks, force_clicks, det, oid_dr, ref_str, err_ref_str, reporter, method, method_other, method_article, comment, tns_type, snad_name, internal_name, tns_mode):

    if not n_clicks and not force_clicks:
        return "", no_update
    
    if not det:
        return html.Div("No detection. Adjust refmag first.", style={"color": "red"}), no_update
    if not reporter or not tns_type or not internal_name:
        return html.Div("Reporter, TNS type, and Internal name are required.", style={"color": "red"}), no_update

    api_key = os.getenv("TNS_API_KEY")
    if not api_key:
        return html.Div("TNS_API_KEY is not set on server.", style={"color": "red"}), no_update

    if tns_mode == "production":
        TNS_HOST = 'www.wis-tns.org'
    else:
        TNS_HOST = 'sandbox.wis-tns.org'
        
    tns_url = f'https://{TNS_HOST}/api'

    bot_id = '87994'
    bot_name = 'SNAD_bot'

    remark = get_remark_text(method, method_other, method_article, comment, oid_dr, internal_name, snad_name)
    phot_remark = helpers.build_phot_remark(internal_name, ref_str, oid_dr["oid"], det["filter"])


    t = Time(det['mjd'], format='mjd', scale='utc')
    discovery_datetime_str = t.iso
    internal_name = helpers.validate_internal_name(internal_name, snad_name, discovery_datetime_str)

    is_force = ctx.triggered_id == "tns-force-submit-btn"

    if not is_force:
        is_dup, tns_name, tns_date, diff_days = await asyncio.to_thread(
            helpers.is_already_submitted, oid_dr["ra"], oid_dr["dec"], discovery_datetime_str
        )
        
        if is_dup:
            if diff_days < 30.0:
                return html.Div([
                    html.Div("Submission Blocked:", style={"color": "red", "fontWeight": "bold", "marginBottom": "5px"}),
                    html.P(f"Object already exists in TNS as {tns_name} with discovery date {tns_date} (differs by {diff_days:.1f} days). Submissions less than 30 days apart are blocked.", style={"margin": "0"})
                ]), {"display": "none"}
            else:
                return html.Div([
                    html.Div("Warning: Object exists in TNS", style={"color": "#FF0000", "fontWeight": "bold", "marginBottom": "5px"}),
                    html.P(f"An object already exists at these coordinates as {tns_name} with discovery date {tns_date} (differs by {diff_days:.1f} days)."),
                    html.P("If you believe this is a new event, click 'FORCE SUBMIT' to proceed.",  style={"fontWeight": "bold"})
                ]), {**BTN_STYLE, "backgroundColor": "#f0ad4e", "color": "white", "display": "inline-flex"}

    figure_url = f"https://ztf.snad.space/{oid_dr['dr']}/figure/{oid_dr['oid']}?format=png"
    uploaded_filename = await asyncio.to_thread(helpers.upload_file_to_tns, figure_url, oid_dr['oid'], tns_url, api_key, bot_id, bot_name)
    payload = helpers.build_payload(oid_dr, det, reporter, tns_type, remark, phot_remark,related_file_name=uploaded_filename)
    payload["at_report"]["0"]["internal_name"] = internal_name
    payload["at_report"]["0"]["photometry"]["photometry_group"]["0"]["flux"] = str(round(det['orig_mag'], 2))
    result, error_msg = await asyncio.to_thread(helpers.submit_report, tns_url, payload, api_key, bot_id, bot_name)    

    if error_msg:
        return html.Div([
            html.Div("TNS submission failed:", style={"color": "#d9534f", "fontWeight": "bold", "marginBottom": "5px"}),
            html.Pre(error_msg, style={"color": "#a94442", "backgroundColor": "#f2dede", "padding": "10px", "borderRadius": "4px", "whiteSpace": "pre-wrap"})
        ]), {"display": "none"}

    catalog_updated = await asyncio.to_thread(
        helpers.update_snad_catalog,
        snad_name, oid_dr["ra"], oid_dr["dec"], oid_dr["oid"], 
        t.iso, det['orig_mag'], det['magerr_down'], det['magerr_up'], 
        ref_str, err_ref_str, result, tns_type, oid_dr.get("ztf_id", "None")
    )

    if catalog_updated:
        catalog_msg = html.Div("SNAD catalog updated.", style={"color": "#666", "fontSize": "14px"})
    else:
        catalog_msg = html.Div("TNS submitted, but failed to update SNAD catalog. Check logs.", style={"color": "red", "fontSize": "14px"})

    return html.Div([
        html.Div("Report sent to TNS.", style={"marginBottom": "5px"}),
        html.Div(f"Received TNS name: {result}", style={"marginBottom": "5px"}),
        catalog_msg
    ], style={"color": "green"}), {"display": "none"}

    
@callback(
    Output("tns-internal-name", "value"),
    Input("tns-det-store", "data"),
    State("tns-internal-name", "value"),
    State("tns-snad-name", "value"),
    State("tns-oid-dr", "data"),
    prevent_initial_call=True
)
def auto_correct_internal_name(det, current_internal_name, snad_name, oid_dr):
    if not det or not current_internal_name or not snad_name or not oid_dr:
        return no_update
    
    t = Time(det['mjd'], format='mjd', scale='utc')
    disc_date = t.iso
    
    original_ztf_id = oid_dr.get("ztf_id", "None")
    
    new_name = helpers.validate_internal_name(current_internal_name, snad_name, disc_date, original_ztf_id)
    
    if new_name != current_internal_name:
        return new_name
    return no_update
