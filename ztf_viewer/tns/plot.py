import plotly.graph_objects as go
import pandas as pd
import numpy as np
from astropy.time import Time

def build_lightcurve_figure(data, det):
    df = pd.DataFrame({
        'mjd': data['mjd'].astype(float),
        'mag': data['mag'].astype(float),
        'magerr': data['magerr'].astype(float),
        'filter': data['filter'].astype(str)
    })
    df = df.replace([np.inf, -np.inf], np.nan).dropna()

    target_filter = det['filter']
    df_filt = df[df['filter'] == target_filter].copy()

    if df_filt.empty:
        return go.Figure()

    t_arr = Time(df_filt['mjd'].values, format='mjd', scale='utc')
    df_filt['date_str'] = t_arr.iso

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_filt['mjd'] - 58000,
        y=df_filt['mag'],
        error_y=dict(type='data', array=df_filt['magerr']),
        mode='markers',
        marker=dict(size=6, color='#2c3e50', opacity=0.8),
        name=f'{target_filter}-band',
        customdata=df_filt[['date_str', 'filter']],
        hovertemplate=(
            "<b>Filter:</b> %{customdata[1]}<br>" +
            "<b>MJD - 58000:</b> %{x:.5f}<br>" +
            "<b>Date:</b> %{customdata[0]}<br>" +
            "<b>Magnitude:</b> %{y:.2f}<br>" +
            "<extra></extra>"
        )
    ))

    det_mjd = float(det['mjd']) - 58000
    det_mag = float(det['orig_mag'])
    
    t_det = Time(det['mjd'], format='mjd', scale='utc')
    det_date = t_det.iso

    fig.add_trace(go.Scatter(
        x=[det_mjd],
        y=[det_mag],
        mode='markers',
        marker=dict(size=15, color='red', symbol='star', line=dict(color='black', width=1)),
        name='Discovery',
        hovertemplate=(
            "<b>Discovery</b><br>" +
            f"<b>Filter:</b> {target_filter}<br>" +
            f"<b>MJD - 58000:</b> {det_mjd:.5f}<br>" +
            f"<b>Date:</b> {det_date}<br>" +
            f"<b>Magnitude:</b> {det_mag:.2f}<br>" +
            "<extra></extra>"
        )
    ))

    fig.add_vline(x=det_mjd, line_dash="dash", line_color="red")

    fig.update_layout(
        title=f"Light Curve ({target_filter}-band)",
        xaxis_title="mjd - 58000",
        yaxis_title="mag",
        height=450,
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor='#ebf0f8',
        hovermode='closest',
        showlegend=False
    )
    
    fig.update_yaxes(autorange="reversed", showgrid=True, gridcolor='white', zeroline=False)
    fig.update_xaxes(showgrid=True, gridcolor='white', zeroline=False)

    return fig
