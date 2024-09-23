# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ERSDialog
                                 A QGIS plugin
 Earth remote sensing
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2024-03-20
        git sha              : $Format:%H$
        copyright            : (C) 2024 by Artem Kovalev
        email                : artem17404@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import shapefile
import numpy as np
from os import path
import pandas as pd
import rasterio as rio
from osgeo import gdal
import geopandas as gpd
from datetime import datetime
from rasterio.mask import mask
from shapely.geometry import mapping, Point
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from PyQt5.QtWidgets import QMessageBox
from qgis.core import QgsCoordinateReferenceSystem
from qgis.core import QgsUnitTypes
from qgis.core import QgsMapLayerProxyModel
from qgis.core import QgsProject

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'earth_remote_sensing_dialog_base.ui'))


class ERSDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(ERSDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        #фильтр растра для дрона(первичная обработка)
        self.FirstRaster_MapLayer_ComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        #фильтр полигонов(первичная обработка)
        self.Polygon_MapLayer_ComboBox.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        #фильтр растра для спутника(первичная обработка)
        self.SecondRaster_MapLayer_ComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        #фильтр точек(самосбоор)
        self.PointField_ComboBox.setFilters(QgsMapLayerProxyModel.PointLayer)
        #фильтр растра для точек(самосбор)
        self.Radius_MapLayer_ComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        #фильтр для создания радиусов
        self.Additional_RasterRadius_MapLayer_ComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        #система измерения радиуса(самосбор)
        self.measurement_system = {'метры': 1, 'километры': 1000, 'сантиметры': 0.01, 'миллиметры': 0.001, 'градусы': 1}
        for MS in self.measurement_system:
            self.RadiusMS_comboBox.addItem(MS)

        #старт программы
        self.StartButton.clicked.connect(self.start)
        #отмена запуска
        self.CancelButton.clicked.connect(self.cancel)

    def reproject_raster(self, file, new_file):
        input_raster = file.source()
        output_path = self.OutPutQgsFileWidget.filePath()
        output_raster = os.path.join(output_path, new_file) + ".tif"
        crs = QgsCoordinateReferenceSystem.authid(self.CS_QgsProjectionSelectionWidget.crs())

        warp_options = gdal.WarpOptions(dstSRS=crs)
        self.warp = gdal.Warp(output_raster, input_raster, options=warp_options)
        self.warp = None
        return (output_raster)

    def reproject_shape(self, file, new_file):
        data = gpd.read_file(file.source())
        crs = QgsCoordinateReferenceSystem.authid(self.CS_QgsProjectionSelectionWidget.crs())
        data = data.to_crs(crs)

        output_path = self.OutPutQgsFileWidget.filePath()
        output_shape = os.path.join(output_path, new_file) + ".shp"
        data.to_file(output_shape)
        return (output_shape)
    
    def data_collection(self, raster_file, table, geoms):
        with rio.open(raster_file) as src:
            no_data = src.nodata
            for idx, geom in enumerate(geoms):
                out_image, out_transform = mask(src, geom, crop=True)
                data = out_image[0, :, :]
                row, col = np.where(data != no_data)
                ndvi = np.extract(data != no_data, data)
            
                T1 = out_transform * rio.Affine.translation(0.5,0.5)
                rc2xy = lambda r, c: (c, r) * T1

                d = gpd.GeoDataFrame({
                    'field_id': [idx+1]*len(ndvi),
                    'col': col,
                    'row': row,
                    'value': ndvi
                })
            
                d['longitude'] = d.apply(lambda row: rc2xy(row.row,row.col)[0], axis = 1)
                d['latitude'] = d.apply(lambda row: rc2xy(row.row,row.col)[1], axis = 1)
                d['geometry'] = d.apply(lambda row: Point(row['longitude'], row['latitude']), axis = 1)
                d = d.set_crs(QgsCoordinateReferenceSystem.authid(self.CS_QgsProjectionSelectionWidget.crs()))
                table = gpd.GeoDataFrame(pd.concat((table, d)))
        return (table)
    
    def output(self, name, output):
        sf = shapefile.Reader(output)
        fields = [x[0] for x in sf.fields][1:]
        records = sf.records()
        shps = [s.points for s in sf.shapes()]

        df = pd.DataFrame(columns = fields, data = records)
        df = df.assign(coord = shps)
        output_path = self.OutPutQgsFileWidget.filePath()
        OUTPUT_PATH = name +'_output.csv'
        output_table = os.path.join(output_path, OUTPUT_PATH)
        df.to_csv(output_table, index = False)
        return (output_table)

    def error(self, text):
        error = QMessageBox()
        error.setWindowTitle("Ошибка при обработке...")
        error.setText(text)
        error.setIcon(QMessageBox.Warning)
        error.setStandardButtons(QMessageBox.Ok)
        error.exec_()

    def cancel(self):
        self.reject()
    
    def start(self):
        start_time = datetime.now()
        output_path = self.OutPutQgsFileWidget.filePath()
        crs = QgsCoordinateReferenceSystem.authid(self.CS_QgsProjectionSelectionWidget.crs())
        units_crs = QgsCoordinateReferenceSystem.mapUnits(self.CS_QgsProjectionSelectionWidget.crs())
        units_ms = QgsUnitTypes.encodeUnit(units_crs)

        units_of_measurements = self.RadiusMS_comboBox.currentText()
        value = self.measurement_system.get(units_of_measurements, None)
        
        first_raster = self.FirstRaster_MapLayer_ComboBox.currentLayer().name()
        polygon = self.Polygon_MapLayer_ComboBox.currentLayer().name()
        second_raster = self.SecondRaster_MapLayer_ComboBox.currentLayer().name()
        
        additional_point_analysis = self.Additional_PointAnalysis_checkBox.isChecked()
        additional_raster_analysis = self.Additional_RasterPoints_checkBox.isChecked()
        additional_general_filter_analysis = self.Additional_GeneralFilter_checkBox.isChecked()

        radius_size = int(self.Radius_QgsSpinBox.text())
        if not crs:
            text = "Вы указали \"пустую\" систему координат!\nИсправьте ошибку для корректной работы!"
            self.error(text)
            return
        if not output_path:
            text = "Вы не указали путь для сохранения результата!\nВнесите изменения перед началом работы!"
            self.error(text)
            return
        if first_raster == second_raster:
            text = "Вы выбрали одинаковые снимки!\nВнесите изменения и повторите еще раз!"
            self.error(text)
            return
        if additional_point_analysis:
            if radius_size == 0:
                text = "Размер радиуса не может быть равен 0!\nВведите корректные данные!"
                self.error(text)
                return
            if units_of_measurements != "градусы" and units_ms == "degrees" or units_of_measurements == "градусы" and units_ms == "meters":
                text = "Выбранные вами Ед. Измер. и Ед. Измер.\nсистемы координат различаются!"
                self.error(text)
                return
        if additional_general_filter_analysis:
            if not additional_point_analysis or not additional_raster_analysis:
                text = "Общий анализ проводится только между двумя таблицами!\nДля одной таблицы результат недоступен!"
                self.error(text)
                return

        first_raster_file = QgsProject.instance().mapLayersByName(first_raster)[0]
        new_first_raster_file = self.FirstRaster_LineEdit.text()
        
        polygon_file = QgsProject.instance().mapLayersByName(polygon)[0]
        new_polygon_file = self.Polygon_LineEdit.text()

        second_raster_file = QgsProject.instance().mapLayersByName(second_raster)[0]
        new_second_raster_file = self.SecondRaster_LineEdit.text()

        reproj_first_raster = self.reproject_raster (first_raster_file, new_first_raster_file)
        reproj_polygon = self.reproject_shape (polygon_file, new_polygon_file)
        reproj_second_raster = self.reproject_raster (second_raster_file, new_second_raster_file)

        #начало работы программы
        shp = gpd.read_file(reproj_polygon)
        geoms = shp.geometry.values
        geom_list = [[mapping(geom)] for geom in geoms]
        #сбор точек с дрона
        first_raster_table = gpd.GeoDataFrame(columns= ['field_id', 'col', 'row', 'value', 'longitude', 'latitude', 'geometry'])
        first_raster_table = first_raster_table.set_geometry('geometry')
        first_raster_table = first_raster_table.set_crs(QgsCoordinateReferenceSystem.authid(self.CS_QgsProjectionSelectionWidget.crs()))
        first_raster_table = self.data_collection(reproj_first_raster, first_raster_table, geom_list)
        clipped_first = gpd.clip(first_raster_table, shp)

        first_raster_values = new_first_raster_file + "_values"
        output_first_raster_file = os.path.join(output_path, first_raster_values) + ".shp"
        clipped_first.to_file(output_first_raster_file, driver = 'ESRI Shapefile')
        self.output(first_raster_values, output_first_raster_file)

        #сбор точек со спутника
        second_raster_table = gpd.GeoDataFrame(columns= ['field_id', 'col', 'row', 'value', 'longitude', 'latitude', 'geometry'])
        second_raster_table = second_raster_table.set_geometry('geometry')
        second_raster_table = second_raster_table.set_crs(QgsCoordinateReferenceSystem.authid(self.CS_QgsProjectionSelectionWidget.crs()))
        second_raster_table = self.data_collection(reproj_second_raster, second_raster_table, geom_list)
        clipped_second = gpd.clip(second_raster_table, shp)

        second_raster_values = new_second_raster_file + "_values"
        output_second_raster_file = os.path.join(output_path, second_raster_values) + ".shp"
        clipped_second.to_file(output_second_raster_file, driver = 'ESRI Shapefile')
        self.output(second_raster_values, output_second_raster_file)

        #проверка на чекбоксе
        if additional_point_analysis:
            #точки для сбора(самосбор)
            point = self.PointField_ComboBox.currentLayer().name()
            point_file = QgsProject.instance().mapLayersByName(point)[0]
            new_point_file = self.Point_LineEdit.text()
            reproj_point = self.reproject_shape(point_file, new_point_file)

            if self.Radius_MapLayer_ComboBox.currentLayer().name() == first_raster:
                input_point_values = output_first_raster_file
            else:
                input_point_values = output_second_raster_file

            radius_file = self.Radius_LineEdit.text()

            field = gpd.read_file(reproj_point)
            point_field = gpd.GeoDataFrame(field)
            point_field['geometry'] = point_field.buffer(radius_size * value)
            clipped_point_field = gpd.clip(point_field, shp)
            output_radius = os.path.join(output_path, radius_file) + ".shp"
            clipped_point_field.to_file(output_radius, driver = 'ESRI Shapefile')

            csv_point_radius = gpd.read_file(input_point_values)
            point_radius_shp = gpd.read_file(output_radius)
            table_radius = gpd.sjoin(csv_point_radius, point_radius_shp, how='inner', op='within')
            del table_radius['Lat'], table_radius['Lon']

            radius_values = radius_file + "_values"
            output_radius_values = os.path.join(output_path, radius_values) + ".shp"
            table_radius.to_file(output_radius_values, driver = 'ESRI Shapefile')
            self.output(radius_values, output_radius_values)

        #Дополнительный анализ для растра
        if additional_raster_analysis:
            additional_raster_radius = self.RasterRadius_LineEdit.text()
            output_raster_radius = os.path.join(output_path, additional_raster_radius) + '.shp'
            
            if self.Additional_RasterRadius_MapLayer_ComboBox.currentLayer().name() == first_raster:
                additional_raster_table = first_raster_table
                input_raster_values = output_second_raster_file
            else:
                additional_raster_table = second_raster_table
                input_raster_values = output_first_raster_file

            additional_raster_table['geometry'] = additional_raster_table.buffer(5, cap_style = 3)
            clipped_table_raster = gpd.clip(additional_raster_table, shp)
            clipped_table_raster.to_file(output_raster_radius, driver = 'ESRI Shapefile')
            
            csv_raster_radius = gpd.read_file(input_raster_values)
            raster_radius_shp = gpd.read_file(output_raster_radius)
            table_raster_radius = gpd.sjoin(csv_raster_radius, raster_radius_shp, how="inner", op="within")

            raster_radius_values = additional_raster_radius + "_values"
            output_raster_radius_values = os.path.join(output_path, raster_radius_values) + ".shp"
            table_raster_radius.to_file(output_raster_radius_values, driver = 'ESRI Shapefile')
            self.output(raster_radius_values, output_raster_radius_values)
        
        #Общий анализ для двух таблиц
        if additional_general_filter_analysis:
            csv_intersection_points = gpd.read_file(output_radius_values)
            intersection_raster_radius_shp = gpd.read_file(output_raster_radius)
            table_intersection = gpd.sjoin(csv_intersection_points, intersection_raster_radius_shp, how="inner", op="within")

            intersection = "overall_result_values"
            output_intersection_values = os.path.join(output_path, intersection) + ".shp"
            table_intersection.to_file(output_intersection_values, driver = 'ESRI Shapefile')
            self.output(intersection, output_intersection_values)
        
        end_time = datetime.now()
        execution_time = end_time - start_time
        text = f"Анализ и обработка успешно закончены!\nВсе файлы находятся в ранее указанной папке!\nВремя работы программы - {execution_time}!"
        self.complete(text)
    
    def complete(self, text):
        complete = QMessageBox()
        complete.setWindowTitle("Завершение анализа!")
        complete.setText(text)
        complete.setIcon(QMessageBox.Information)
        complete.setStandardButtons(QMessageBox.Ok)
        complete.exec_()