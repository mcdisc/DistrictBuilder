/*
 * Create an OpenLayers.Layer.WMS type layer.
 *
 * @param name The name of the layer (appears in the layer switcher).
 * @param layer The layer name (or array of names) served by the WMS server.
 * @param extents The extents of the layer -- must be used for GeoWebCache.
 */
function createLayer( name, layer, extents ) {
    return new OpenLayers.Layer.WMS( name,
        'http://' + MAP_SERVER + '/geoserver/gwc/service/wms',
        { srs: 'EPSG:3785',
          layers: layer,
          tiles: 'true',
          tilesOrigin: extents.left + ',' + extents.bottom,
          format: 'image/png'
        },
	{
	  displayOutsideMaxExtent: true
	}
    );
}

function getSnapLayer() {
    return $('#snapto').val();
}

function getShowBy() {
    return $('#showby').val();
}

function getBoundLayer() {
    return $('#boundfor').val();
}

/*
 * Initialize the map. This method is called by the onload page event.
 */
function init() {
    OpenLayers.ProxyHost= "/proxy?url=";

    // set up sizing for dynamic map size that fills the pg
    //resizemap();
    //window.onresize = resizemap;

    // The extents of the layers. These extents will depend on the study
    // area; the following are the bounds for the web cache around Ohio.
    // TODO Make the initial layer extents configurable. Maybe fetch them
    // from geowebcache
    var layerExtent = new OpenLayers.Bounds(
        -9442154.0,
        4636574.5,
        -8868618.0,
        5210110.5
    );

    // This projection is web mercator
    var projection = new OpenLayers.Projection('EPSG:3785');

    var navigate = new OpenLayers.Control.Navigation({
        autoActivate: true,
        handleRightClicks: true
    });

    // Create a slippy map.
    var olmap = new OpenLayers.Map('map', {
        // The resolutions here must match the settings in geowebcache.
        // TODO Fetch these resolutions from geowebcache
	resolutions: [2035.2734375, 1017.63671875, 508.818359375, 254.4091796875, 127.20458984375, 63.602294921875, 31.8011474609375, 15.90057373046875, 7.950286865234375, 3.9751434326171875, 1.9875717163085938, 0.9937858581542969, 0.49689292907714844, 0.24844646453857422, 0.12422323226928711, 0.062111616134643555, 0.031055808067321777, 0.015527904033660889, 0.007763952016830444, 0.003881976008415222, 0.001940988004207611, 9.704940021038055E-4, 4.8524700105190277E-4, 2.4262350052595139E-4, 1.2131175026297569E-4],
        maxExtent: layerExtent,
        projection: projection,
        units: 'm',
        controls: [
            navigate,
            new OpenLayers.Control.PanZoomBar()
        ]
    });

    // These layers are dependent on the layers available in geowebcache
    // TODO Fetch a list of layers from geowebcache
    var layers = [];
    for (layer in MAP_LAYERS) {
        layers.push(createLayer( MAP_LAYERS[layer], MAP_LAYERS[layer], layerExtent ));
    }

    var match = window.location.href.match(new RegExp('/plan\/(\\d+)\/edit/'));
    var plan_id = match[1];
    var districtStrategy = new OpenLayers.Strategy.Fixed({preload:true});
    
    var districtLayer = new OpenLayers.Layer.Vector(
        'Current Plan',
        {
            strategies: [
                districtStrategy
            ],
            protocol: new OpenLayers.Protocol.WFS({
                url: 'http://' + MAP_SERVER + '/geoserver/wfs',
                featureType: 'simple_district',
                featureNS: 'http://gmu.azavea.com/',
                featurePrefix: 'gmu',
                geometryName: 'geom',
                srsName: 'EPSG:3785' 
            }),
            styleMap: new OpenLayers.StyleMap({
                fill: true,
                fillOpacity: 0.01,
                strokeColor: '#ee9900',
                strokeOpacity: 1,
                strokeWidth: 2
            }),
            projection:projection,
            filter: new OpenLayers.Filter.Comparison({
                type: OpenLayers.Filter.Comparison.EQUAL_TO,
                property: 'plan_id',
                value: plan_id
            })
        }
    );

    var selection = new OpenLayers.Layer.Vector('Selection',{
        styleMap: new OpenLayers.StyleMap({
            "default": new OpenLayers.Style(
                OpenLayers.Util.applyDefaults(
                    { 
                        fill: false, 
                        strokeColor: '#ffff00', 
                        strokeWidth: 3 
                    }, 
                    OpenLayers.Feature.Vector.style["default"]
                )
            ),
            "select":  new OpenLayers.Style(
                OpenLayers.Util.applyDefaults(
                    { 
                        fill: true, 
                        fillColor: '#ee9900',
                        strokeColor: '#ee9900'
                    }, 
                    OpenLayers.Feature.Vector.style["select"]
                )
            )
        })
    });

    layers.push(districtLayer);
    layers.push(selection);
    olmap.addLayers(layers);

    var getProtocol = new OpenLayers.Protocol.WFS({
        url: 'http://' + MAP_SERVER + '/geoserver/wfs',
        featureType: getSnapLayer(),
        featureNS: 'http://gmu.azavea.com/',
        featurePrefix: 'gmu',
        srsName: 'EPSG:3785',
        geometryName: 'geom'
    });

    var getControl = new OpenLayers.Control.GetFeature({
        autoActivate: false,
        protocol: getProtocol,
        multipleKey: 'shiftKey'
    });

    var boxControl = new OpenLayers.Control.GetFeature({
        autoActivate: false,
        protocol: getProtocol,
        box: true
    });

    var jsonParser = new OpenLayers.Format.JSON();
    var lastTool = null;

    var assignOnSelect = function(feature) {
        if (selection.features.length == 0)
            return;

        var district_id = feature.data.district_id;
        var geolevel_id = selection.features[0].attributes.geolevel_id;
        var geounit_ids = [];
        for (var i = 0; i < selection.features.length; i++) {
            geounit_ids.push( selection.features[i].attributes.id );
        }
        geounit_ids = geounit_ids.join('|');
        OpenLayers.Element.addClass(olmap.viewPortDiv,'olCursorWait');
        OpenLayers.Request.POST({
            method: 'POST',
            url: '/districtmapping/plan/' + plan_id + '/district/' + district_id + '/add',
            params: {
                geolevel: geolevel_id,
                geounits: geounit_ids
            },
            success: function(xhr) {
                var data = jsonParser.read(xhr.responseText);
                if (data.success) {
                    districtStrategy.load();
                }
                selection.drawFeature(selection.features[0], 'select');

                var selector = olmap.getControlsByClass('OpenLayers.Control.SelectFeature')[0];
                selector.deactivate();

                if (lastTool !== null) {
                    lastTool.activate();
                }

                $('#assign_district').val('-1');
            },
            failure: function(xhr) {
                window.status = 'failed to select';
            }
        });
    };

    var assignControl = new OpenLayers.Control.SelectFeature(
        districtLayer,
        {
            autoActivate: false,
            onSelect: assignOnSelect
        }
    );

    var polyControl = new OpenLayers.Control.DrawFeature( 
        selection,
        OpenLayers.Handler.Polygon,
        {
            featureAdded: function(feature){
                var newOpts = getControl.protocol.options;
                newOpts.featureType = getSnapLayer();
                getControl.protocol = new OpenLayers.Protocol.WFS( newOpts );
                getControl.protocol.read({
                    filter: new OpenLayers.Filter.Spatial({
                        type: OpenLayers.Filter.Spatial.INTERSECTS,
                        value: feature.geometry,
                        projection: getProtocol.options.srsName
                    }),
                    callback: function(rsp){
                        selection.removeFeatures(selection.features);
                        selection.addFeatures(rsp.features);
                    }
                });
            }
        }
    );


    var featureSelected = function(e){
        selection.addFeatures([e.feature]);
    };
    getControl.events.register('featureselected', this, featureSelected);
    boxControl.events.register('featureselected', this, featureSelected);

    var featureUnselected = function(e){
        selection.removeFeatures([e.feature]);
    };
    getControl.events.register('featureunselected', this, featureUnselected);
    boxControl.events.register('featureunselected', this, featureUnselected);

    districtLayer.events.register('loadstart',districtLayer,function(){
        OpenLayers.Element.addClass(olmap.viewPortDiv, 'olCursorWait');
    });
    districtLayer.events.register('loadend',districtLayer,function(){
        OpenLayers.Element.removeClass(olmap.viewPortDiv, 'olCursorWait');
        selection.removeFeatures(selection.features);
        
        $('#assign_district').empty();
        $('<option />').attr('value', '-1').text('-- Select One --').appendTo('#assign_district');

        var sorted = districtLayer.features.slice(0,districtLayer.features.length);
        sorted.sort(function(a,b){
            return a.attributes.name > b.attributes.name;
        });

        $.each(sorted, function(n, feature) {
            $('<option />').attr('value', feature.attributes.id).text( feature.attributes.name).appendTo('#assign_district');
        });
    });

    $('#navigate_map_tool').click(function(evt){
        navigate.activate();
        getControl.deactivate();
        boxControl.deactivate();
        polyControl.deactivate();
        assignControl.deactivate();
        selection.removeFeatures(selection.features);
    });

    $('#single_drawing_tool').click(function(evt){
        getControl.activate();
        boxControl.deactivate();
        navigate.deactivate();
        polyControl.deactivate();
        assignControl.deactivate();
        selection.removeFeatures(selection.features);
    });

    $('#rectangle_drawing_tool').click(function(evt){
        boxControl.activate();
        getControl.deactivate();
        navigate.deactivate();
        polyControl.deactivate();
        assignControl.deactivate();
        selection.removeFeatures(selection.features);
    });

    $('#polygon_drawing_tool').click(function(evt){
        boxControl.deactivate();
        getControl.deactivate();
        navigate.deactivate();
        polyControl.activate();
        assignControl.deactivate();
        selection.removeFeatures(selection.features);
    });

    $('#assign_tool').click(function(evt){
        lastTool = olmap.getControlsBy('active',true)[0];
        boxControl.deactivate();
        getControl.deactivate();
        navigate.deactivate();
        polyControl.deactivate();
        assignControl.activate();
    });

    olmap.addControls([
        getControl,
        boxControl,
        polyControl,
        assignControl
    ]);

    $('#snapto').change(function(evt){
        var newOpts = getControl.protocol.options;
        newOpts.featureType = getSnapLayer();
        getControl.protocol = 
            boxControl.protocol = new OpenLayers.Protocol.WFS( newOpts );
    });

    $('#showby').change(function(evt){
        var boundary = getBoundLayer();
        var layers = olmap.getLayersByName('gmu:demo_' + boundary + '_' + evt.target.value);
        olmap.setBaseLayer(layers[0]);
    });

    $('#boundfor').change(function(evt){
        var show = getShowBy();
        var layers = olmap.getLayersByName('gmu:demo_' + evt.target.value + '_' + show);
        olmap.setBaseLayer(layers[0]);
    });

    $('#assign_district').change(function(evt){
        if (this.value == '-1'){
            return;
        }

        var feature = { data:{ district_id: this.value } };
        assignOnSelect(feature);
    });

    // Set the initial map extents to the bounds around the study area.
    // TODO Make these configurable.
    olmap.zoomToExtent(new OpenLayers.Bounds(-9467000,4570000,-8930000,5170000));
    OpenLayers.Element.addClass(olmap.viewPortDiv, 'olCursorWait');
}
