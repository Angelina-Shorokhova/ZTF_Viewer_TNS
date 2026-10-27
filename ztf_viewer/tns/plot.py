import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_lightcurve_figure(data, det, ref):
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Relative flux", "Magnitude"))

    fig.add_trace(
        go.Scatter(
            x=data['mjd'], y=data['flux'],
            error_y=dict(type='data', array=data['fluxerr']),
            mode='markers', marker=dict(size=4), name='flux',
        ),
        row=1, col=1,
    )
    fig.add_vline(x=det['mjd'], line_dash='dash', line_color='red', row=1, col=1)
    fig.add_trace(
        go.Scatter(x=[det['mjd']], y=[det['flux']], mode='markers',
                   marker=dict(size=12, color='red'), name='1st detection'),
        row=1, col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=data['mjd'], y=data['mag'],
            error_y=dict(
                type='data', symmetric=False,
                array=data['magerr_up'].tolist(),
                arrayminus=data['magerr_down'].tolist(),
            ),
            mode='markers', marker=dict(size=4), name='mag',
        ),
        row=1, col=2,
    )
    fig.add_vline(x=det['mjd'], line_dash='dash', line_color='red', row=1, col=2)
    fig.add_hline(y=ref, line_dash='dash', line_color='black', row=1, col=2)
    fig.update_yaxes(autorange='reversed', row=1, col=2)
    fig.update_layout(height=380, margin=dict(l=40, r=20, t=40, b=40))
    return fig
