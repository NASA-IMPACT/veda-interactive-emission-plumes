import panel as pn

pn.extension("ipywidgets", sizing_mode="stretch_width")
import io
import requests
import ipywidgets as widgets
import matplotlib.pyplot as plt
import matplotlib as mpl
from ipyleaflet import Map, TileLayer, WidgetControl, GeoJSON, ScaleControl
from datetime import date, timedelta

session = requests.session()

def fetch_json(url):
    return session.get(url).json()


GITHUB_URL = "https://raw.githubusercontent.com/NASA-IMPACT/veda-interactive-emission-plumes/main/content/Methane Metadata.json"

result = fetch_json(GITHUB_URL)

def set_id(x):
    i, f  = x
    f["id"] = i
    return f

outlines = list(map(set_id, enumerate(filter(lambda f: f["geometry"]["type"] == "Polygon", result["features"]))))
centers = list(map(set_id, enumerate(filter(lambda f: f["geometry"]["type"] == "Point", result["features"]))))


# Get the ids for every item in the STAC collection
STAC_SEARCH_URL = "https://dev.ghg.center/api/stac/search?collections=nasa-jpl-plumes-emissions-updated&fields=id,geometry,properties&limit=1000"

result = fetch_json(STAC_SEARCH_URL)


item_ids = result["features"]

VMIN = 0
VMAX = 1500
IDS_ON_MAP = set()

m = Map(center=(39, -98), zoom=4, scroll_wheel_zoom=True)
#m.layout.min_height = "800px"
m.layout.height="100%"
m.layout.width="100%"

polygons = GeoJSON(
    data={"features": outlines}, 
    name='outlines',
    style={"color": "blue"},
    hover_style={'color': 'red'},
)

pins = GeoJSON(
    data={"features": centers}, 
    name='centers',
)
position_label = widgets.Label(layout=widgets.Layout(padding="10px", width="160px"), style={"background": "#ffffff66"})
def handle_interaction(**kwargs):
    if kwargs.get('type') == 'mousemove':
        lon, lat = kwargs.get('coordinates')
        position_label.value = f"W {round(lat, 4)}, N {round(lon, 4)}"

m.on_interaction(handle_interaction)

out = widgets.Output(layout=widgets.Layout(width="700px"))
colorbar_widget = widgets.Output(layout=widgets.Layout(width="450px"))


# create date range slider and callback for filtering data
start_date = date.fromisoformat(centers[0]["properties"]["UTC Time Observed"].split("T")[0])
end_date = date.fromisoformat(centers[-1]["properties"]["UTC Time Observed"].split("T")[0])

vmax_fixed = widgets.Checkbox(
    description=f"Fix max value of colorbar to {VMAX} (ppm m). Click plume again to update.",
    style={'description_width': 'initial'},
    layout=widgets.Layout(width="450px")
)

# create date range slider and callback for filtering data
start_date = date.fromisoformat(centers[0]["properties"]["UTC Time Observed"].split("T")[0])
end_date = date.fromisoformat(centers[-1]["properties"]["UTC Time Observed"].split("T")[0])

delta = end_date - start_date   # returns timedelta
dates = [(start_date + timedelta(days=i)).isoformat() for i in range(delta.days + 1)]



date_range = widgets.SelectionRangeSlider(
    options=dates,
    index=(0, len(dates) - 1),
    orientation='horizontal',
    layout={'width': '300px'},
    style={'description_width': 'initial'},
    readout=False
)

start_label = widgets.Label(date_range.value[0])
end_label = widgets.Label(date_range.value[-1])


def filter_by_time(item, start, end):
    t = item["properties"]["UTC Time Observed"]
    return t > start and t < end

def filter_data(start, end):
    global outlines
    global centers
    
    func = lambda x: filter_by_time(x, start, end)
    pins.data = {"features": list(filter(func, centers))}
    polygons.data = {"features": list(filter(func, outlines))}


def dts_callback(dts):
    start = dts[0]
    end = dts[1]
    start_label.value = start
    end_label.value = end
    filter_data(start, end)


widgets.interactive_output(dts_callback, {"dts": date_range})

date_range_widget = widgets.HBox([start_label, date_range, end_label])

m.add(polygons)
m.add(pins)
m.add(WidgetControl(widget=out, position="bottomleft"))
m.add(WidgetControl(widget=date_range_widget, position="topright"))
m.add(WidgetControl(widget=colorbar_widget, position="topright", transparent_bg=True))
m.add(WidgetControl(widget=position_label, position="bottomright", transparent_bg=True))
m.add(ScaleControl(position='bottomright'))


@out.capture(clear_output=True)
def display_properties(feature):
    p = {k: v for k, v in feature["properties"].items() if k not in ["style"]}
    return p
    # #display(pd.Series(p))
    # json_widget = pn.pane.JSON(pd.Series(p), height=75)
    # #pn.pane.JSON(pd.Series(p))



@colorbar_widget.capture(clear_output=True)
def create_colorbar():
    colorbar_fig, ax = plt.subplots(figsize=(6, 1));
    colorbar_fig.subplots_adjust(bottom=0.5);

    cb = mpl.colorbar.ColorbarBase(
        ax,
        cmap=mpl.cm.plasma,
        norm=mpl.colors.Normalize(vmin=VMIN, vmax=VMAX),
        orientation='horizontal'
    )
    cb.set_label('Plume Concentration (ppm m)')
    f = io.BytesIO()
    colorbar_fig.savefig(f, bbox_inches='tight', format='png')
    image = f.getvalue()
    # Create an Image widget from the saved image
    output = widgets.Image(value=image, format='png')

    colorbar_control = WidgetControl(widget=output, position='bottomright', transparent_bg=True)
    plt.close(colorbar_fig)

    return colorbar_control

def add_raster(feature):
    global item_ids
    global m
    
    props = feature["properties"]

    collection = "nasa-jpl-plumes-emissions-updated"
    assets = "ch4-plume-emissions"

    if feature["id"] not in IDS_ON_MAP:
        from shapely.geometry import shape
        subset = [i for i in item_ids if i["id"].startswith(props["Scene FID"])]
        outline_shape = shape(outlines[int(feature["id"])]["geometry"])
        for item in subset:
            if shape(item["geometry"]).intersects(outline_shape):
                TILE_URL = (
                    'https://dev.ghg.center/api/raster/stac/tiles/WebMercatorQuad/{z}/{x}/{y}@1x'
                    f'?collection={collection}&item={item["id"]}&assets={assets}'
                    f'&resampling=bilinear&bidx=1&colormap_name=plasma&rescale={VMIN}%2C{VMAX}&nodata=-9999'
                )
                m.add(TileLayer(url=TILE_URL, max_zoom=24, show_loading=True))
        IDS_ON_MAP.add(feature["id"])
    if len(IDS_ON_MAP) == 1:
        
        colorbar_control = create_colorbar()
        m.add(colorbar_control)
    # for control in m.controls:
    #     if isinstance(control, WidgetControl):
    #         if control.position == "bottomright":
    #             m.remove(control)

    

    #m.add_layer(aggr)
    if m.zoom < 12:
        m.center = (props['Latitude of max concentration'], props['Longitude of max concentration'])
        m.zoom = 12


def set_date_range(feature):
    global date_range
    props = feature["properties"]
    
    t = date.fromisoformat(props["UTC Time Observed"].split("T")[0])
    date_range.value = ((t - timedelta(days=1)).isoformat(), (t + timedelta(days=1)).isoformat())


def on_click(event, feature, **kwargs):
    p = display_properties(feature)
    add_raster(feature)
    set_date_range(feature)
    json_widget.object = p


polygons.on_click(on_click)
pins.on_click(on_click)

json_widget = pn.pane.JSON({})
component = pn.Column(
    pn.panel(m, sizing_mode="stretch_both", min_height=500),
    json_widget
)

ACCENT_BASE_COLOR = "#0C3D91"
template = pn.template.FastListTemplate(
    site="",
    title="",
    logo="https://d36s2ep3ahcq5b.cloudfront.net/browseui/assets/us_ghg_logo.png",
    favicon="https://d36s2ep3ahcq5b.cloudfront.net/browseui/favicon.ico",
    header_background=ACCENT_BASE_COLOR,
    accent_base_color=ACCENT_BASE_COLOR,
    main=[component],
).servable()

