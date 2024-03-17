#https://dash.plotly.com/dash-core-components/checklist
#https://www.arduino.cc/reference/en/iot/api/#api-PropertiesV2-propertiesV2Show
#https://github.com/arduino/iot-client-py/blob/master/example/main.py
#https://blog.networktocode.com/post/using-python-requests-with-rest-apis/
#https://www.geeksforgeeks.org/how-to-update-a-plot-on-same-figure-during-the-loop/
#https://plotly.com/python/scattermapbox/
#https://www.youtube.com/watch?v=H16dZMYmvqo
#https://stackoverflow.com/questions/68866089/can-i-save-a-high-resolution-image-of-my-plotly-scatter-plot
#https://dash.plotly.com/dash-core-components/dropdown
#https://dash.plotly.com/dash-daq/booleanswitch
#https://plotly.com/python/interactive-html-export/
#https://community.plotly.com/t/heatmap-mapbox-for-displaying-weather-maps/34150
#https://www.matecdev.com/posts/point-in-polygon.html 

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
import requests
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from shapely.geometry import Point, Polygon
import numpy as np
from base64 import b64encode
import io

#Creating class to facilitate averaging of PM values within each grid and to determine min and max colourscale values
class heat():
    mini = None
    maxi = None

    def __init__(self, size):
        self.value = [[] for _ in range(size**2)]
        self.avg = [[None] for _ in range(size**2)]
        self.index = [i for i in range(size**2)]

    def add(self, loc, val):
        self.value[loc].append(val)
        self.avg[loc] = np.mean(self.value[loc])
        if heat.mini == None:
            heat.mini = val
        elif val < heat.mini:
            heat.mini = val
        if heat.maxi == None:
            heat.maxi = heat.mini + 0.01 #prevents min and max from being equal
        elif heat.maxi < val:
            heat.maxi = val

#Tokens and Keys for mapbox and Arduino IoT cloud
mapbox_access_token = 'pk.eyJ1IjoidHRuMWcyMSIsImEiOiJjbHNvbWV0NmYwNWppMmpuamg1YzhxeGZmIn0.PEn-3qudCiL0l8QMA659JQ'
CLIENT_ID = 'T9npD#!lcIh9!PYj24XHquVCg76XZ8G2'  
CLIENT_SECRET = 's!i#4#TuqSTmyB8YfLbDy3g5ITSIBcRPIf6T?3trzZvDtUkcJ2yvltBdq@FOLBrU'

#Creating OAuth session to obtain token to access PM and location data from arduino IoT Cloud
oauth_client = BackendApplicationClient(client_id=CLIENT_ID)
token_url = "https://api2.arduino.cc/iot/v1/clients/token"
oauth = OAuth2Session(client=oauth_client)

#Creating Geojson for grid
size = 30
start_latitude = 50.9381
end_latitude = 50.932867
start_longitude = -1.400685
end_longitude = -1.391683

latitude_step = (start_latitude-end_latitude) / size
longitude_step = (end_longitude - start_longitude) / size

geojson = {
    "type": "FeatureCollection",
    "features": []
}

for i in range(size):
    for j in range(size):

        cell_coordinates = [
            [start_longitude + (j + 1) * longitude_step, start_latitude - i * latitude_step],
            [start_longitude + (j + 1) * longitude_step, start_latitude - (i + 1) * latitude_step],
            [start_longitude + j * longitude_step, start_latitude - (i + 1) * latitude_step],
            [start_longitude + j * longitude_step, start_latitude - i * latitude_step]]
        
        feature = {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [cell_coordinates]
            },
            "id": f"{i * size + j}"
        }
        geojson["features"].append(feature)


#creating instance of heat class to store avg PM in each grid
pm1 = heat(size)
pm25 = heat(size)
pm10 = heat(size)

app = Dash(__name__)
server = app.server

encoded = ''

#Configuring settings to save plot as image
config = {
  'toImageButtonOptions': {
    'format': 'png', 
    'filename': 'new_plot',
    'height': 1000,
    'width': 900,
    'scale':10 
  }
}

#Setting the layout of the Dash app
app.layout = html.Div([
    dcc.Graph(id='live-update-graph'),
    dcc.Interval(
        id='interval-component',
        interval=3000,  # Update graph every 2 seconds
        n_intervals=0
    ),
    dcc.Dropdown(options=[
                {'label': 'PM1', 'value': 1},
                {'label': 'PM2.5', 'value': 2},
                {'label': 'PM10', 'value': 3}
            ], 
            value=3, id='demo-dropdown'),
    html.Div(id='dd-output-container'),
    dcc.Checklist(
        id='check',
        options = [{'label': 'Show Buildings', 'value':1}],
        value = []
        ),
    html.A(
        html.Button("Download Map"),
        id="download",
        href="",
        download="PM_map.html"
    )
])

@app.callback(
    Output('live-update-graph', 'figure'),
    Output('download', 'href'),
    Input('interval-component', 'n_intervals'),
    Input('demo-dropdown', 'value'),
    Input('check', 'value')
)
def update_map(n, value, box):
    #obtaining Arduino IoT Cloud token
    token = oauth.fetch_token(
        token_url=token_url,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        include_client_id=True,
        audience="https://api2.arduino.cc/iot",
    )

    token = token['access_token']

    #Retrieving data from Arduino IoT cloud
    url = 'https://api2.arduino.cc/iot/v2/things/c3a71f6c-e861-49af-83dc-755f53f03647'

    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(url, headers=headers)
    resp = response.json()

    #PM concentrations measured in μg/m^3
    p1 = resp['properties'][0]['last_value']
    p25 = resp['properties'][2]['last_value']
    p10 = resp['properties'][1]['last_value']

    #Latitude and longitude from mobile phone - retrived from arduino IoT cloud
    lat = resp['properties'][3]['last_value']['lat']
    lon = resp['properties'][3]['last_value']['lon']

    #performing point-in-polygon tests, then averaging PM values within each grid
    for j in range(size**2):
            pnt = Point(lon, lat)
            ply = Polygon(geojson['features'][j]['geometry']['coordinates'][0])
            if pnt.within(ply):
                pm10.add(j, p10)
                pm25.add(j, p25)
                pm1.add(j, p1)
                break

    #Chooses which plot to display, and what text to show over the legend depending on dropdown menu
    if value == 3:
        z = pm10.avg
        title = 'PM10'
    elif value == 2:
        z = pm25.avg
        title = 'PM2.5'
    elif value == 1:
        z = pm1.avg
        title = 'PM1'
    
    #Deciding which basemap to use depending on checklist status
    if 1 in box:
        style = 'mapbox://styles/ttn1g21/cltotjat9006t01qw0r5se71n'
        opacity = 0.8
    else:
        style = 'light'
        opacity = 0.4

    #Creating figure
    fig = go.Figure(data=go.Choroplethmapbox(
        geojson=geojson,
        locations=pm1.index,
        z=z,
        zmin=heat.mini,   
        zmax=heat.maxi, 
        colorscale=[[0, f'rgba(68,1,84,{opacity})'], [0.2, f'rgba(59,82,139,{opacity})'], [0.4, f'rgba(33,144,141,{opacity})'], 
                [0.6, f'rgba(144,206,79,{opacity})'], [0.8, f'rgba(253,231,37,{opacity})'], [1, f'rgba(253,231,37,{opacity})']],
        marker_line_width=0.4,
        showscale=True,
        text = f'{title} Concentration (μg/m^3)',
        colorbar=dict(title=f'{title} [μg/m³]')
        ))
    
    fig.update_layout(width=1000, height=900,
        margin={"r":0, "t":0, "l":0, "b":0},
        mapbox=dict(
            accesstoken= mapbox_access_token,
            center=dict(
                lat=50.9354835,
                lon=-1.396184
            ),
            style = style,
            zoom=16,
        ),
    )

    #writing plot to html file to be saved locally
    buffer = io.StringIO()
    fig.write_html(buffer)

    html_bytes = buffer.getvalue().encode()
    encoded = b64encode(html_bytes).decode()

    return fig, f"data:text/html;base64,{encoded}"

if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=1000)
