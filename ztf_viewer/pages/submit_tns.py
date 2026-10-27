import asyncio
import os
import urllib.parse

import pandas as pd
from astropy.table import Table
from astropy.time import Time
from dash import Input, Output, State, callback, ctx, dcc, html, no_update

from ztf_viewer.tns import helpers
from ztf_viewer.tns.plot import build_lightcurve_figure


TNS_TYPES = [
    {"label": "PSN (supernova)", "value": "PSN"},
    {"label": "PNV (nova)", "value": "PNV"},
    {"label": "AGN", "value": "AGN"},
    {"label": "NUC (nuclear transient)", "value": "NUC"},
    {"label": "FRB", "value": "FRB"},
]

ALGORITHMS = [
    {"label": "AAD", "value": "AAD"},
    {"label": "PineForest", "value": "PineForest"},
    {"label": "Miner (similarity)", "value": "Miner"},
    {"label": "Signature", "value": "Signature"},
    {"label": "Other (enter your own)", "value": "Custom"},
]


async def get_layout(pathname, search):
    params = {k: v[0] for k, v in urllib.parse.parse_qs(search.lstrip("?")).items()}
    oid = params.get("oid", "")
    dr = params.get("dr", "dr24")
    back_href = f"/{dr}/view/{oid}" if oid and dr else "/"

    lc = await asyncio.to_thread(helpers.load_snad_data, oid, dr)
    ra, dec = await asyncio.to_thread(helpers.get_ra_dec, oid)

    if lc is None or len(lc) == 0:
        return html.Div(
            [
                html.H2("Submit to TNS"),
                html.P(f"Could not load SNAD light curve for {oid} ({dr}).", style={"color": "red"}),
                dcc.Link("Back", href=back_href),
            ],
            style={"padding": "20px"},
        )

    tail = lc['mag'][-10:] if len(lc) >= 10 else lc['mag']
    default_ref = float(round(float(pd.Series(tail).median()), 2))
    default_mjd_start = float(lc['mjd'].min()) - 5

    lc_json = {
        "mjd": lc['mjd'].tolist(),
        "mag": lc['mag'].tolist(),
        "magerr": lc['magerr'].tolist(),
        "filter": lc['filter'].tolist(),
        "clrcoeff": (lc['clrcoeff'].tolist() if 'clrcoeff' in lc.colnames
                     else [0.0] * len(lc)),
    }

    return html.Div(
        [
            dcc.Store(id="tns-lc-store", data=lc_json),
            dcc.Store(id="tns-oid-dr", data={"oid": oid, "dr": dr, "ra": ra, "dec": dec}),
            dcc.Store(id="tns-det-store"),

            html.H2("Submit to TNS"),

            html.Div([html.Label("OID:"),
                      dcc.Input(id="tns-oid", value=oid, disabled=True, style={"width": "300px"})]),
            html.Div([html.Label("RA, DEC (deg):"),
                      dcc.Input(id="tns-coords",
                                value=f"{ra}, {dec}" if ra is not None else "—",
                                disabled=True, style={"width": "300px"})]),
            html.Div([html.Label("SNAD name:"),
                      dcc.Input(id="tns-snad-name", value=oid, disabled=True,
                                style={"width": "300px"})]),

            html.Div([
                html.Label("Refmag:"),
                dcc.Input(id="tns-refmag", type="number", value=default_ref, step=0.01,
                          style={"width": "120px"}),
                html.Label("Err refmag:", style={"marginLeft": "20px"}),
                dcc.Input(id="tns-err-refmag", type="number", value=0.1, step=0.01,
                          style={"width": "120px"}),
                html.Label("MJD start:", style={"marginLeft": "20px"}),
                dcc.Input(id="tns-mjd-start", type="number", value=default_mjd_start, step=0.1,
                          style={"width": "140px"}),
            ], style={"marginTop": "12px"}),

            html.Div([
                html.Label("Reporter:"),
                dcc.Input(id="tns-reporter", type="text", placeholder="Your name",
                          style={"display": "block", "marginBottom": "12px", "width": "300px"}),
            ], style={"marginTop": "12px"}),
            html.Div([
                html.Label("Method:"),
                dcc.Dropdown(id="tns-method", options=ALGORITHMS, value="AAD",
                             style={"width": "300px"}),
                dcc.Input(id="tns-method-other", type="text",
                          placeholder="Enter your method",
                          style={"display": "none", "marginTop": "8px", "width": "300px"}),
            ]),
            html.Div([
                html.Label("Comment:"),
                dcc.Textarea(id="tns-comment", style={"width": "300px", "height": "70px"}),
            ], style={"marginTop": "12px"}),
            html.Div([
                html.Label("TNS type:"),
                dcc.Dropdown(id="tns-type", options=TNS_TYPES, value="NUC",
                             style={"width": "300px"}),
            ], style={"marginTop": "12px"}),

            dcc.Loading(dcc.Graph(id="tns-graph")),
            html.Div(id="tns-extracted",
                     style={"marginTop": "12px", "fontFamily": "monospace"}),

            html.Label("Generated report text (for review):", style={"marginTop": "16px"}),
            html.Div(id="tns-generated-text",
                     style={"whiteSpace": "pre-wrap", "border": "1px solid #ccc",
                            "padding": "10px", "background": "#f8f8f8", "width": "80%"}),

            html.Div([
                dcc.Link("Back", href=back_href, style={"marginRight": "12px"}),
                html.Button("Submit to TNS", id="tns-submit-button", n_clicks=0),
            ], style={"marginTop": "16px"}),
            dcc.Loading(html.Div(id="tns-submit-output", style={"marginTop": "16px"})),
        ],
        style={"padding": "20px", "maxWidth": "1200px"},
    )


@callback(
    Output("tns-method-other", "style"),
    Input("tns-method", "value"),
)
def toggle_method_other(method):
    if method == "Custom":
        return {"display": "block", "marginTop": "8px", "width": "300px"}
    return {"display": "none"}


@callback(
    Output("tns-graph", "figure"),
    Output("tns-extracted", "children"),
    Output("tns-det-store", "data"),
    Input("tns-refmag", "value"),
    Input("tns-err-refmag", "value"),
    Input("tns-mjd-start", "value"),
    State("tns-lc-store", "data"),
)
def update_plot(ref, err_ref, mjd_start, lc_json):
    if not lc_json or ref is None or err_ref is None or mjd_start is None:
        return no_update, no_update, no_update
    lc = Table.from_pandas(pd.DataFrame(lc_json))
    enriched = helpers.enrich_data(lc, ref, err_ref)
    det = helpers.find_first_detection(enriched, mjd_start)
    if det is None:
        return no_update, "No detection found — adjust MJD start or refmag.", None
    fig = build_lightcurve_figure(enriched, det, ref)
    t = Time(det['mjd'], format='mjd', scale='utc')
    extracted = html.Div([
        html.B(f"Discovery date (UT): {t.iso}"), html.Br(),
        f"MJD: {det['mjd']:.5f}", html.Br(),
        f"Magnitude: {det['orig_mag']:.2f} ± {det['magerr']:.2f}", html.Br(),
        f"Error down: {det['magerr_down']:.2f}, up: {det['magerr_up']:.2f}", html.Br(),
        f"Filter: {det['filter']}",
    ])
    return fig, extracted, det


@callback(
    Output("tns-generated-text", "children"),
    Input("tns-method", "value"),
    Input("tns-method-other", "value"),
    Input("tns-comment", "value"),
    Input("tns-reporter", "value"),
    Input("tns-type", "value"),
    State("tns-det-store", "data"),
    State("tns-oid-dr", "data"),
    State("tns-refmag", "value"),
)
def update_generated_text(method, method_other, comment, reporter, tns_type,
                          det, oid_dr, ref):
    if not det or not oid_dr:
        return "(waiting for detection)"
    algorithm = method_other if method == "Custom" else method
    remark = helpers.build_remark(algorithm, oid_dr["oid"], "None",
                                  oid_dr["oid"], custom_remark=method_other or "")
    phot_remark = helpers.build_phot_remark("None", ref, oid_dr["oid"], det["filter"])
    return (
        f"Reporter: {reporter or '—'}\n"
        f"Type: {tns_type or '—'}\n"
        f"Method: {algorithm or '—'}\n"
        f"Comment: {comment or '—'}\n"
        f"\nRemarks: {remark}\n"
        f"Photometry remarks: {phot_remark}"
    )
