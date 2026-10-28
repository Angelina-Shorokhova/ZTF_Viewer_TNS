import plotly.graph_objects as go
import pandas as pd

def build_lightcurve_figure(data, det):
    df = pd.DataFrame({
        'mjd': data['mjd'].astype(float) - 58000,
        'mag': data['mag'].astype(float),
        'magerr': data['magerr'].astype(float),
        'filter': data['filter'].astype(str)
    }).dropna()

    target_filter = det['filter']
    df_filt = df[df['filter'] == target_filter]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_filt['mjd'],
        y=df_filt['mag'],
        error_y=dict(type='data', array=df_filt['magerr']),
        mode='markers',
        marker=dict(size=5, color='#2c3e50', opacity=0.8),
        name=f'{target_filter}-band'
    ))

    det_mjd = float(det['mjd']) - 58000
    det_mag = float(det['orig_mag'])
    
    fig.add_trace(go.Scatter(
        x=[det_mjd],
        y=[det_mag],
        mode='markers',
        marker=dict(size=15, color='red', symbol='star'),
        name='Discovery'
    ))

    fig.add_vline(x=det_mjd, line_dash="dash", line_color="red")

    fig.update_layout(
        title=f"Light Curve ({target_filter}-band)",
        xaxis_title="MJD - 58000",
        yaxis_title="mag",
        height=400,
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor='white'
    )
    fig.update_yaxes(autorange="reversed", showgrid=True, gridcolor='#eee')
    fig.update_xaxes(showgrid=True, gridcolor='#eee')

    return fig
