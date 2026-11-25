import plotly.graph_objects as go
import pandas as pd
import numpy as np
from astropy.time import Time

MJD_OFFSET = 58000

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
    
    df_filt = df_filt.sort_values(by='mag', ascending=False)

    fig = go.Figure()

    color_map = {
        'zg': '#62D03E',
        'zr': '#CC3344',
        'zi': '#1c1309'
    }
    target_color = color_map.get(target_filter, 'gray')

    fig.add_trace(go.Scatter(
        x=df_filt['mjd'] - MJD_OFFSET,
        y=df_filt['mag'],
        error_y=dict(
            type='data', 
            array=df_filt['magerr'], 
            color=target_color, 
            thickness=1
        ),
        mode='markers',
        marker=dict(
            size=10, 
            color=target_color, 
            line=dict(width=0.5, color="black")
        ),
        name=f'{target_filter}-band',
        customdata=df_filt[['date_str', 'filter']],
        hovertemplate=(
            "<b>Filter:</b> %{customdata[1]}<br>" +
            f"<b>MJD - {MJD_OFFSET}:</b> %{{x:.5f}}<br>" +
            "<b>Date:</b> %{customdata[0]}<br>" +
            "<b>Magnitude:</b> %{y:.2f}<br>" +
            "<extra></extra>"
        )
    ))

    det_mjd = float(det['mjd']) - MJD_OFFSET
    det_mag = float(det['orig_mag'])
    det_date = Time(det['mjd'], format='mjd', scale='utc').iso

    fig.add_trace(go.Scatter(
        x=[det_mjd],
        y=[det_mag],
        mode='markers',
        marker=dict(
            size=10, 
            color='gold', 
            symbol='star',
            line=dict(width=0.5, color="black")
        ),
        name='Discovery',
        hovertemplate=(
            "<b>Discovery</b><br>" +
            f"<b>Filter:</b> {target_filter}<br>" +
            f"<b>MJD - {MJD_OFFSET}:</b> {det_mjd:.5f}<br>" +
            f"<b>Date:</b> {det_date}<br>" +
            f"<b>Magnitude:</b> {det_mag:.2f}<br>" +
            "<extra></extra>"
        )
    ))


    fig.update_layout(
        title=dict(
            text=f"Light curve ({target_filter}-band)", 
            font=dict(color="black"), 
            x=0.5, 
            xanchor="center"
        ),
        xaxis_title=f"mjd - {MJD_OFFSET}",
        yaxis_title="mag",
        height=450,
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor='#E8E8E8',
        hovermode='closest',
        showlegend=False
    )
    
    fig.update_yaxes(
        autorange="reversed", 
        showgrid=True, 
        gridcolor='white', 
        zeroline=False,
        tickfont=dict(color="black"), 
        title_font=dict(color="black"),
        title_standoff=0
    )
    
    fig.update_xaxes(
        showgrid=True, 
        gridcolor='white', 
        zeroline=False,
        tickfont=dict(color="black"), 
        title_font=dict(color="black"),
        title_standoff=0
    )

    return fig
