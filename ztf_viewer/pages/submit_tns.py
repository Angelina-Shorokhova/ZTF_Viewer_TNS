import asyncio
import os
import json
import urllib.parse
import pandas as pd
from astropy.table import Table
from astropy.time import Time
from dash import Input, Output, State, callback, dcc, html, no_update

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
            html.H2("Submit to TNS", style={"marginBottom": "20px"}),
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
            ], style={"display": "flex", "gap": "20px", "marginBottom": "20px"}),

            dcc.Loading(dcc.Graph(id="tns-graph", config={'displayModeBar': True, 'displaylogo': False})),

            html.Div(id="tns-extracted", style={"marginTop": "15px", "fontFamily": "monospace", "fontSize": "18px", "backgroundColor": "#fff", "padding": "15px", "borderLeft": "5px solid #f1c40f", "boxShadow": "0 2px 5px rgba(0,0,0,0.1)"}),

            html.Label("Generated TNS Payload (Review):", style={"fontWeight": "bold", "marginTop": "25px"}),
            html.Pre(id="tns-generated-text", style={"whiteSpace": "pre-wrap", "border": "1px solid #ddd", "padding": "15px", "backgroundColor": "#fafafa", "fontSize": "12px", "marginBottom": "20px", "maxHeight": "300px", "overflowY": "scroll"}),

            html.Div([
                dcc.Link("BACK TO OBJECT", href=back_href, style=BTN_STYLE),
                html.Button("SUBMIT REPORT", id="tns-submit-button", n_clicks=0, style=BTN_STYLE),
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
    Input("tns-refmag", "value"), Input("tns-err-refmag", "value"),
    State("tns-lc-store", "data"),
)
def update_plot(ref_str, err_ref_str, lc_json):
    try:
        ref = float(ref_str)
        err_ref = float(err_ref_str)
    except (ValueError, TypeError):
        return no_update, "Invalid numeric values.", None

    if not lc_json:
        return no_update, no_update, no_update
        
    lc = Table.from_pandas(pd.DataFrame(lc_json))
    enriched = helpers.enrich_data(lc, ref, err_ref)
    
    mjd_start = float(lc['mjd'].min()) - 10
    det = helpers.find_first_detection(enriched, mjd_start)
    
    if det is None:
        return no_update, "No detection found. Adjust refmag.", None
        
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

    remark = get_remark_text(method, method_other, method_article, comment, oid_dr, internal_name, snad_name)
    phot_remark = helpers.build_phot_remark(internal_name, ref_str, oid_dr["oid"], det["filter"]) 
    
    payload = helpers.build_payload(oid_dr, det, reporter, tns_type, remark, phot_remark)
    payload["at_report"]["0"]["internal_name"] = internal_name
    payload["at_report"]["0"]["photometry"]["photometry_group"]["0"]["flux"] = str(round(det['orig_mag'], 2))
    
    return json.dumps(payload, indent=4)

@callback(
    Output("tns-submit-output", "children"),
    Input("tns-submit-button", "n_clicks"),
    State("tns-det-store", "data"), State("tns-oid-dr", "data"), State("tns-refmag", "value"),
    State("tns-reporter", "value"), State("tns-method", "value"), State("tns-method-other", "value"),
    State("tns-method-article", "value"), State("tns-comment", "value"), State("tns-type", "value"),
    State("tns-snad-name", "value"), State("tns-internal-name", "value"),
    prevent_initial_call=True,
)
async def handle_submit(n_clicks, det, oid_dr, ref_str, reporter, method, method_other, method_article, comment, tns_type, snad_name, internal_name):
    if not n_clicks:
        return ""
    if not det:
        return html.Div("No detection. Adjust refmag first.", style={"color": "red"})
    if not reporter or not tns_type or not internal_name:
        return html.Div("Reporter, TNS type, and Internal name are required.", style={"color": "red"})

    api_key = os.getenv("TNS_API_KEY")
    tns_url = os.getenv("TNS_API_URL", "https://sandbox.wis-tns.org/api")
    bot_id = os.getenv("TNS_BOT_ID", helpers.BOT_ID)
    bot_name = os.getenv("TNS_BOT_NAME", helpers.BOT_NAME)
    
    if not api_key:
        return html.Div("TNS_API_KEY is not set on server.", style={"color": "red"})

    remark = get_remark_text(method, method_other, method_article, comment, oid_dr, internal_name, snad_name)
    phot_remark = helpers.build_phot_remark(internal_name, ref_str, oid_dr["oid"], det["filter"])
    
    payload = helpers.build_payload(oid_dr, det, reporter, tns_type, remark, phot_remark)
    payload["at_report"]["0"]["internal_name"] = internal_name
    payload["at_report"]["0"]["photometry"]["photometry_group"]["0"]["flux"] = str(round(det['orig_mag'], 2))

    result = await asyncio.to_thread(helpers.submit_report, tns_url, payload, api_key, bot_id, bot_name)
    
    if not result:
        return html.Div("TNS submission failed. Check server logs.", style={"color": "red"})
    
    t = Time(det['mjd'], format='mjd', scale='utc')
    await asyncio.to_thread(
        helpers.update_snad_catalog,
        internal_name, oid_dr["ra"], oid_dr["dec"], oid_dr["oid"], 
        t.iso, det['orig_mag'], det['magerr_down'], det['magerr_up'], 
        ref_str, "0.1", result, tns_type, oid_dr.get("ztf_id", "None")
    )
    
    return html.Div([
        html.Div("Report sent to TNS.", style={"marginBottom": "5px"}),
        html.Div(f"Received TNS name: {result}", style={"marginBottom": "5px"}),
        html.Div("SNAD catalog updated.", style={"color": "#666", "fontSize": "14px"})
    ], style={"color": "green"})
