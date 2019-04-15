import pandas as pd
import numpy as np
import arcpy


# define environ
class GetPaths():
    def __init__(self):
        self.enviro = "C:/Users/paulinkenbrandt/AppData/Roaming/Esri/Desktop10.6/ArcCatalog/Connection to DEFAULT@uggp.agrc.utah.gov.sde"
        self.chemistry_table = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Phy_Chem_Results"
        self.activities_table = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Phy_Chem_Activities"
        self.stations_table = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Locations"


class SDEStationstoWQX(object):

    def __init__(self, sde_stat_table, save_dir):
        self.import_config_link = "https://cdx.epa.gov/WQXWeb/ImportConfigurationDetail.aspx?mode=import&impcfg_uid=6441"
        sde_stat_import = sde_stat_table[sde_stat_table['inwqx'] == 0]
        sde_stat_import = sde_stat_import.reset_index()
        sde_stat_import['TribalLandInd'] = 'No'
        sde_stat_import['TribalLandName'] = None
        sde_stat_import = sde_stat_import.apply(lambda x: self.get_context(x), 1)
        self.stat_col_order = self.get_stat_col_order()
        sde_stat_import = sde_stat_import[self.stat_col_order]
        sde_stat_import = sde_stat_import[sde_stat_import['LocationType'] != 'Barometer']
        self.sde_stat_import = sde_stat_import.sort_values("LocationID")
        self.save_dir = save_dir

    def save_file(self):
        self.sde_stat_import.to_csv(self.save_dir + "/stations_{:%Y%m%d}.csv".format(pd.datetime.today()), index=False)


    def get_stat_col_order(self):
        stat_col_import_order = ['LocationID', 'LocationName', 'LocationType', 'HUC8', 'HUC12',
                                 'TribalLandInd', 'TribalLandName', 'Latitude', 'Longitude',
                                 'HorizontalCollectionMethod', 'HorizontalCoordRefSystem',
                                 'State', 'County',
                                 'VerticalMeasure', 'VerticalUnit', 'VerticalCoordRefSystem',
                                 'VerticalCollectionMethod',
                                 'AltLocationID', 'AltLocationContext',
                                 'WellType', 'WellDepth', 'WellDepthMeasureUnit', 'AquiferName']
        return stat_col_import_order

    def get_context(self, df):
        if pd.isnull(df['USGS_ID']):
            if pd.isnull(df['WIN']):
                if pd.isnull(df['WRNum']):
                    df['AltLocationContext'] = None
                    df['AltLocationID'] = None
                else:
                    df['AltLocationContext'] = 'Utah Water Rights Number'
                    df['AltLocationID'] = df['WRNum']
            else:
                df['AltLocationContext'] = 'Utah Well ID'
                df['AltLocationID'] = df['WIN']
        else:
            df['AltLocationContext'] = 'USGS ID'
            df['AltLocationID'] = df['USGS_ID']
        return df

def edit_table(df, sde_table, fieldnames=None,
               enviro="C:/Users/paulinkenbrandt/AppData/Roaming/Esri/Desktop10.6/ArcCatalog/UGS_SDE.sde"):
    """
    this function will append rows to an existing SDE table from a pandas dataframe. It requires editing privledges.
    :param df: pandas dataframe with data you wish to append to SDE table
    :param fieldnames: names of fields you wish to import
    :param sde_table: name of sde table
    :param enviro: path to connection file of the SDE
    :return:
    """
    arcpy.env.workspace = enviro

    if len(fieldnames) > 0:
        pass
    else:
        fieldnames = df.columns

    read_descr = arcpy.Describe(sde_table)
    sde_field_names = []
    for field in read_descr.fields:
        sde_field_names.append(field.name)
    sde_field_names.remove('OBJECTID')

    for name in fieldnames:
        if name not in sde_field_names:
            fieldnames.remove(name)
            print("{:} not in {:} fieldnames!".format(name, sde_table))

    try:
        egdb_conn = arcpy.ArcSDESQLExecute(enviro)
        egdb_conn.startTransaction()
        print("Transaction started...")
        # Perform the update
        try:
            # build the sql query to pull the maximum object id
            sqlid = """SELECT max(OBJECTID) FROM {:};""".format(sde_table)
            objid = egdb_conn.execute(sqlid)

            subset = df[fieldnames]
            rowlist = subset.values.tolist()
            # build the insert sql to append to the table
            sqlbeg = "INSERT INTO {:}({:},OBJECTID)\nVALUES ".format(sde_table, ",".join(map(str, fieldnames)))
            sqlendlist = []

            for j in range(len(rowlist)):
                objid += 1
                strfill = []
                # This loop deals with different data types and NULL values
                for k in range(len(rowlist[j])):
                    if pd.isna(rowlist[j][k]):
                        strvar = "NULL"
                    elif isinstance(rowlist[j][k], (int, float)):
                        strvar = "{:}".format(rowlist[j][k])
                    else:
                        strvar = "'{:}'".format(rowlist[j][k])
                    if k == 0:
                        strvar = "(" + strvar
                    strfill.append(strvar)
                strfill.append(" {:})".format(objid))
                sqlendlist.append(",".join(map(str, strfill)))

            sqlend = "{:}".format(",".join(sqlendlist))
            sql = sqlbeg + sqlend
            #print(sql)
            egdb_return = egdb_conn.execute(sql)

            # If the update completed successfully, commit the changes.  If not, rollback.
            if egdb_return == True:
                egdb_conn.commitTransaction()
                print("Committed Transaction")
            else:
                egdb_conn.rollbackTransaction()
                print("Rolled back any changes.")
                print("++++++++++++++++++++++++++++++++++++++++\n")
        except Exception as err:
            print(err)
            egdb_return = False
        # Disconnect and exit
        del egdb_conn
    except Exception as err:
        print(err)

def compare_sde_wqx(wqx_results_filename, enviro, chem_table_name, table_type='chem'):
    """
    compares unique rows in an SDE chem table to that of a WQX download
    :param wqx_results_filename: excel file with wqx results download
    :param enviro: file location or sde connection file location of table
    :param chem_table_name: table with chemistry data in SDE
    :return:
    """
    arcpy.env.workspace = enviro

    wqx_chem_table = pd.read_excel(wqx_results_filename)

    sde_chem_table = table_to_pandas_dataframe(chem_table_name)

    if table_type == 'chem':
        wqx_chem_table['uniqueid'] = wqx_chem_table[['Monitoring Location ID', 'Activity ID', 'Characteristic']].apply(
            lambda x: "{:}-{:}-{:}".format(str(x[0]), str(x[1]), x[2]), 1)
        sde_chem_table['uniqueid'] = sde_chem_table[['MonitoringLocationID', 'ActivityID', 'CharacteristicName']].apply(
            lambda x: "{:}-{:}-{:}".format(str(x[0]), str(x[1]), x[2]), 1)
        wqx_chem_table = wqx_chem_table.set_index('uniqueid')
        sde_chem_table = sde_chem_table.set_index('uniqueid')
    else:
        sde_chem_table = sde_chem_table.set_index('LocationID')
        wqx_chem_table = wqx_chem_table.set_index('Monitoring Location ID')

    objtable = []

    for ind in sde_chem_table.index:
        if ind in wqx_chem_table.index:
            objtable.append(sde_chem_table.loc[ind, 'OBJECTID'])
    loc_dict = {}  # empty dictionary
    # iterate input table
    with arcpy.da.UpdateCursor(chem_table_name, ['OID@', 'inwqx']) as tcurs:
        for row in tcurs:
            # index location row[2]=SHAPE@X and row[1]=SHAPE@Y that matches index locations in dictionary
            if row[0] in objtable:
                row[1] = 1
                tcurs.updateRow(row)

    sde_chem_table = table_to_pandas_dataframe(chem_table_name)
    return wqx_chem_table, sde_chem_table

def table_to_pandas_dataframe(table, field_names=None, query=None, sql_sn=(None, None)):
    """
    Load data into a Pandas Data Frame for subsequent analysis.
    :param table: Table readable by ArcGIS.
    :param field_names: List of fields.
    :param query: SQL query to limit results
    :param sql_sn: sort fields for sql; see http://pro.arcgis.com/en/pro-app/arcpy/functions/searchcursor.htm
    :return: Pandas DataFrame object.
    """
    # TODO Make fast with SQL
    # if field names are not specified
    if not field_names:
        field_names = get_field_names(table)
    # create a pandas data frame
    df = pd.DataFrame(columns=field_names)

    # use a search cursor to iterate rows
    with arcpy.da.SearchCursor(table, field_names, query, sql_clause=sql_sn) as search_cursor:
        # iterate the rows
        for row in search_cursor:
            # combine the field names and row items together, and append them
            df = df.append(dict(zip(field_names, row)), ignore_index=True)

    # return the pandas data frame
    return df


def get_field_names(table):
    read_descr = arcpy.Describe(table)
    field_names = []
    for field in read_descr.fields:
        field_names.append(field.name)
    field_names.remove('OBJECTID')
    return field_names


class ProcessEPASheet(object):

    def __init__(self, file_path, save_path, schema_file_path, user='paulinkenbrandt'):
        self.enviro = "C:/Users/paulinkenbrandt/AppData/Roaming/Esri/Desktop10.6/ArcCatalog/Connection to DEFAULT@uggp.agrc.utah.gov.sde"
        arcpy.env.workspace = self.enviro
        self.chem_table_name = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Phy_Chem_Results"
        self.activities_table_name = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Phy_Chem_Activities"
        self.stations_table_name = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Locations"
        self.user = user
        self.save_folder = save_path
        self.schema_file_path = schema_file_path

        self.epa_raw_data = pd.read_excel(file_path)
        self.epa_data = None
        self.epa_rename = {'Laboratory': 'LaboratoryName',
                           'LabNumber': 'ActivityID',
                           'SampleName': 'MonitoringLocationID',
                           'Method': 'ResultAnalyticalMethodID',
                           'Analyte': 'CharacteristicName',
                           'ReportLimit': 'ResultDetecQuantLimitUnit',
                           'Result': 'resultvalue',
                           'AnalyteQual': 'ResultQualifier',
                           'AnalysisClass': 'ResultSampleFraction',
                           'ReportLimit': 'DetecQuantLimitMeasure',
                           'Units':'ResultUnit',
                           }

        self.epa_drop = ['Batch', 'Analysis', 'Analyst', 'CASNumber', 'Elevation', 'LabQual',
                         'Client', 'ClientMatrix', 'Dilution', 'SpkAmt', 'UpperLimit', 'Recovery',
                         'Surrogate', 'LowerLimit', 'Latitude', 'Longitude', 'SampleID', 'ProjectNumber',
                         'Sampled', 'Analyzed', 'PrepMethod', 'Prepped', 'Project']

    def renamepar(self, df):

        x = df['CharacteristicName']
        pardict = {'Ammonia as N': ['Ammonia', 'as N'], 'Sulfate as SO4': ['Sulfate', 'as SO4'],
                   'Nitrate as N': ['Nitrate', 'as N'], 'Nitrite as N': ['Nitrite', 'as N'],
                   'Orthophosphate as P': ['Orthophosphate', 'as P']}
        if ' as' in x:
            df['CharacteristicName'] = pardict.get(x)[0]
            df['MethodSpeciation'] = pardict.get(x)[1]
        else:
            df['CharacteristicName'] = df['CharacteristicName']
            df['MethodSpeciation'] = None

        return df

    def hasless(self, df):
        if '<' in str(df['resultvalue']):
            df['resultvalue'] = None
            df['ResultDetectionCondition'] = 'Below Reporting Limit'
            df['ResultDetecQuantLimitType'] = 'Lower Reporting Limit'
        elif '>' in str(df['resultvalue']):
            df['resultvalue'] = None
            df['ResultDetectionCondition'] = 'Above Reporting Limit'
            df['ResultDetecQuantLimitType'] = 'Upper Reporting Limit'
        elif '[' in str(df['resultvalue']):
            df['resultvalue'] = pd.to_numeric(df['resultvalue'].split(" ")[0],errors='coerce')
            df['ResultDetecQuantLimitType'] = None
            df['ResultDetectionCondition'] = None
        else:
            df['resultvalue'] = pd.to_numeric(df['resultvalue'],errors='coerce')
            df['ResultDetecQuantLimitType'] = None
            df['ResultDetectionCondition'] = None
        return df

    def resqual(self, x):
        if pd.isna(x[1]) and x[0] == 'Below Reporting Limit':
            return 'BRL'
        elif pd.notnull(x[1]):
            return x[1]
        else:
            return None

    def filtmeth(self, x):
        if "EPA" in x:
            x = x.split(' ')[1]
        elif '/' in x:
            x = x.split('/')[0]
        else:
            x = x
        return x

    def save_it(self, savefolder):
        self.epa_data.to_csv("{:}/epa_sheet_to_sde_{:%Y%m%d%M%H%S}.csv".format(savefolder, pd.datetime.today()))

    def get_group_names(self):
        char_schema = pd.read_excel(self.schema_file_path, "CHARACTERISTIC")
        chemgroups = char_schema[['Name', 'Group Name']].set_index(['Name']).to_dict()['Group Name']
        return chemgroups

    def run_calcs(self):
        epa_raw_data = self.epa_raw_data
        epa_raw_data = epa_raw_data.rename(columns=self.epa_rename)
        epa_raw_data['ResultSampleFraction'] = epa_raw_data['ResultSampleFraction'].apply(
            lambda x: 'Total' if 'WET' else x, 1)
        epa_raw_data['personnel'] = None
        epa_raw_data = epa_raw_data.apply(lambda x: self.hasless(x), 1)
        epa_raw_data['ResultAnalyticalMethodID'] = epa_raw_data['ResultAnalyticalMethodID'].apply(
            lambda x: self.filtmeth(x), 1)
        epa_raw_data['ResultAnalyticalMethodContext'] = 'USEPA'
        epa_raw_data['ProjectID'] = 'UNGWMN'
        epa_raw_data['ResultQualifier'] = epa_raw_data[['ResultDetectionCondition',
                                                        'ResultQualifier']].apply(lambda x: self.resqual(x), 1)
        epa_raw_data['inwqx'] = 0
        epa_raw_data['notes'] = None
        epa_raw_data = epa_raw_data.apply(lambda x: self.renamepar(x), 1)
        epa_raw_data['resultid'] = epa_raw_data[['ActivityID','CharacteristicName']].apply(lambda x: str(x[0]) + '-' + str(x[1]), 1)
        epa_raw_data['ActivityStartDate'] = epa_raw_data['Sampled'].apply(lambda x: "{:%Y-%m-%d}".format(x), 1)
        epa_raw_data['ActivityStartTime'] = epa_raw_data['Sampled'].apply(lambda x: "{:%H:%M}".format(x), 1)
        epa_raw_data['AnalysisStartDate'] = epa_raw_data['Analyzed'].apply(lambda x: "{:%Y-%m-%d}".format(x), 1)
        unitdict = {'ug/L': 'ug/l', 'NONE': 'None', 'UMHOS-CM': 'uS/cm', 'mg/L':'mg/l'}
        epa_raw_data['ResultUnit'] = epa_raw_data['ResultUnit'].apply(lambda x: unitdict.get(x, x), 1)
        epa_raw_data['ResultDetecQuantLimitUnit'] = epa_raw_data['ResultUnit']

        chemgroups = self.get_group_names()
        epa_raw_data['characteristicgroup'] = epa_raw_data['CharacteristicName'].apply(lambda x: chemgroups.get(x),1)

        epa_data = epa_raw_data.drop(self.epa_drop, axis=1)
        self.epa_data = epa_data
        self.save_it(self.save_folder)
        return epa_data

    def append_data(self):
        epa_chem = self.run_calcs()
        sdeact = table_to_pandas_dataframe(self.activities_table_name,
                                           field_names=['MonitoringLocationID', 'ActivityID'])
        sdechem = table_to_pandas_dataframe(self.chem_table_name, field_names=['MonitoringLocationID', 'ActivityID'])

        epa_chem['created_user'] = self.user
        epa_chem['last_edited_user'] = self.user
        epa_chem['created_date'] = pd.datetime.today()
        epa_chem['last_edited_date'] = pd.datetime.today()

        try:
            df = epa_chem[~epa_chem['ActivityID'].isin(sdeact['ActivityID'])]
            fieldnames = ['ActivityID', 'ProjectID', 'MonitoringLocationID', 'ActivityStartDate',
                          'ActivityStartTime', 'notes', 'personnel', 'created_user', 'created_date', 'last_edited_user',
                          'last_edited_date']

            for i in range(0, len(df), 500):
                j = i + 500
                if j > len(df):
                    j = len(df)
                subset = df.iloc[i:j]
                print("{:} to {:} complete".format(i, j))
                edit_table(subset, self.activities_table_name, fieldnames=fieldnames, enviro=self.enviro)
                print('success!')
        except Exception as err:
            print(err)
            print('fail!')
            pass

        try:
            df = epa_chem[~epa_chem['ActivityID'].isin(sdechem['ActivityID'])]
            fieldnames = ['ActivityID', 'MonitoringLocationID', 'ResultAnalyticalMethodContext',
                          'ResultAnalyticalMethodID',
                          'ResultSampleFraction',
                          'resultvalue', 'DetecQuantLimitMeasure', 'ResultDetecQuantLimitUnit', 'ResultUnit',
                          'AnalysisStartDate', 'ResultDetecQuantLimitType', 'ResultDetectionCondition',
                          'CharacteristicName',
                          'MethodSpeciation', 'characteristicgroup', 'resultid',
                          'inwqx', 'created_user', 'last_edited_user', 'created_date', 'last_edited_date']

            for i in range(0, len(df), 500):
                j = i + 500
                if j > len(df):
                    j = len(df)
                subset = df.iloc[i:j]
                print("{:} to {:} complete".format(i, j))
                edit_table(subset, self.chem_table_name, fieldnames=fieldnames, enviro=self.enviro)
                print('success!')
        except Exception as err:
            print(err)
            print('fail!')
            pass



class ProcessStateLabText(object):

    def __init__(self, file_path, save_path, sample_matches_file, schema_file_path, user = 'paulinkenbrandt'):
        self.enviro = "C:/Users/paulinkenbrandt/AppData/Roaming/Esri/Desktop10.6/ArcCatalog/Connection to DEFAULT@uggp.agrc.utah.gov.sde"
        arcpy.env.workspace = self.enviro
        self.chem_table_name = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Phy_Chem_Results"
        self.activities_table_name = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Phy_Chem_Activities"
        self.stations_table_name = "UGGP.UGGPADMIN.UGS_NGWMN_Monitoring_Locations"
        self.user = user
        self.save_folder = save_path
        self.schema_file_path = schema_file_path
        self.sample_matches_file = sample_matches_file

        self.state_lab_chem = pd.read_csv(file_path, sep="\t")

        self.param_explain = {'Fe': 'Iron', 'Mn': 'Manganese', 'Ca': 'Calcium',
                              'Mg': 'Magnesium', 'Na': 'Sodium',
                              'K': 'Potassium', 'HCO3': 'Bicarbonate',
                              'CO3': 'Carbonate', 'SO4': 'Sulfate',
                              'Cl': 'Chloride', 'F': 'Floride', 'NO3-N': 'Nitrate as Nitrogen',
                              'NO3': 'Nitrate', 'B': 'Boron', 'TDS': 'Total dissolved solids',
                              'Total Dissolved Solids': 'Total dissolved solids',
                              'Hardness': 'Total hardness', 'hard': 'Total hardness',
                              'Total Suspended Solids': 'Total suspended solids',
                              'Cond': 'Conductivity', 'pH': 'pH', 'Cu': 'Copper',
                              'Pb': 'Lead', 'Zn': 'Zinc', 'Li': 'Lithium', 'Sr': 'Strontium',
                              'Br': 'Bromide', 'I': 'Iodine', 'PO4': 'Phosphate', 'SiO2': 'Silica',
                              'Hg': 'Mercury', 'NO3+NO2-N': 'Nitrate + Nitrite as Nitrogen',
                              'As': 'Arsenic', 'Cd': 'Cadmium', 'Ag': 'Silver',
                              'Alk': 'Alkalinity, total', 'P': 'Phosphorous',
                              'Ba': 'Barium', 'DO': 'Dissolved oxygen',
                              'Q': 'Discharge', 'Temp': 'Temperature',
                              'Hard_CaCO3': 'Hardness as Calcium Carbonate',
                              'DTW': 'Depth to water',
                              'O18': 'Oxygen-18', '18O': 'Oxygen-18', 'D': 'Deuterium',
                              'd2H': 'Deuterium', 'C14': 'Carbon-14',
                              'C14err': 'Carbon-14 error', 'Trit_err': 'Tritium error',
                              'Meas_Alk': 'Alkalinity, total', 'Turb': 'Turbidity',
                              'TSS': 'Total suspended solids',
                              'C13': 'Carbon-13', 'Tritium': 'Tritium',
                              'S': 'Sulfur', 'density': 'density',
                              'Cr': 'Chromium', 'Se': 'Selenium',
                              'temp': 'Temperature', 'NO2': 'Nitrite',
                              'O18err': 'Oxygen-18 error', 'd2Herr': 'Deuterium error',
                              'NaK': 'Sodium + Potassium', 'Al': 'Aluminum',
                              'Be': 'Beryllium', 'Co': 'Cobalt',
                              'Mo': 'Molydenum', 'Ni': 'Nickel',
                              'V': 'Vanadium', 'SAR': 'Sodium absorption ratio',
                              'Hard': 'Total hardness', 'Free Carbon Dioxide': 'Carbon dioxide',
                              'CO2': 'Carbon dioxide'
                              }
        self.chemcols = {'Sample Number': 'ActivityID',
                         'Station ID': 'MonitoringLocationID',
                         'Sample Date': 'ActivityStartDate',
                         'Sample Time': 'ActivityStartTime',
                         'Sample Description': 'notes',
                         'Collector': 'personnel',
                         'Method Agency': 'ResultAnalyticalMethodContext',
                         'Method ID': 'ResultAnalyticalMethodID',
                         'Matrix Description': 'ResultSampleFraction',
                         'Result Value': 'resultvalue',
                         'Lower Report Limit': 'DetecQuantLimitMeasure',
                         'Method Detect Limit': 'ResultDetecQuantLimitUnit',
                         'Units': 'ResultUnit',
                         'Analysis Date': 'AnalysisStartDate'}

        self.proj_name_matches = {'Arches Monitoring Wells': 'UAMW',
                                  'Bryce': 'UBCW',
                                  'Castle Valley': 'CAVW',
                                  'GSL Chem': 'GSLCHEM',
                                  'Juab Valley': 'UJVW',
                                  'Mills/Mona Wetlands': 'MMWET',
                                  'Monroe Septic': 'UMSW',
                                  'Ogden Valley': 'UOVW',
                                  'Round Valley': 'URVH',
                                  'Snake Valley': 'USVW', 'Snake Valley Wetlands': 'SVWET',
                                  'Tule Valley Wetlands': 'TVWET', 'UGS-NGWMN': 'UNGWMN',
                                  'WRI - Grouse Creek': 'UWRIG',
                                  'WRI - Montezuma': 'UWRIM',
                                  'WRI - Tintic Valley': 'UWRIT'}

        self.fieldnames = ['ActivityID', 'ProjectID', 'MonitoringLocationID', 'ActivityStartDate',
                           'ActivityStartTime', 'notes', 'personnel', 'created_user',
                           'created_date', 'last_edited_user', 'last_edited_date']

        self.labfields = ['ActivityID', 'MonitoringLocationID',
                          'ResultAnalyticalMethodContext', 'ResultAnalyticalMethodID',
                          'ResultSampleFraction', 'resultvalue', 'DetecQuantLimitMeasure',
                          'ResultDetecQuantLimitUnit', 'ResultUnit', 'AnalysisStartDate',
                          'ResultDetecQuantLimitType', 'ResultDetectionCondition',
                          'CharacteristicName', 'MethodSpeciation', 'characteristicgroup',
                          'ResultValueType', 'ResultStatusID']


    def run_calcs(self):
        matches_dict = self.get_sample_matches()
        state_lab_chem = self.state_lab_chem
        state_lab_chem['Station ID'] = state_lab_chem['Sample Number'].apply(lambda x: matches_dict.get(x), 1)
        state_lab_chem['ResultDetecQuantLimitType'] = 'Lower Reporting Limit'

        projectmatch = self.get_proj_match()
        state_lab_chem['ProjectID'] = state_lab_chem['Station ID'].apply(lambda x: projectmatch.get(x), 1)
        state_lab_chem['ProjectID'] = state_lab_chem['ProjectID'].apply(lambda x: self.proj_name_matches.get(x), 1)
        state_lab_chem['Matrix Description'] = state_lab_chem['Matrix Description'].apply(lambda x: self.ressampfr(x),
                                                                                          1)
        state_lab_chem['ResultDetectionCondition'] = state_lab_chem[['Problem Identifier', 'Result Code']].apply(
            lambda x: self.lssthn(x), 1)
        state_lab_chem['Sample Date'] = pd.to_datetime(state_lab_chem['Sample Date'].str.split(' ', expand=True)[0])
        state_lab_chem['Analysis Date'] = pd.to_datetime(state_lab_chem['Analysis Date'].str.split(' ', expand=True)[0])
        state_lab_chem = state_lab_chem.apply(lambda df: self.renamepar(df), 1)
        state_lab_chem = state_lab_chem.rename(columns=self.chemcols)
        chemgroups = self.get_group_names()
        state_lab_chem['characteristicgroup'] = state_lab_chem['CharacteristicName'].apply(lambda x: chemgroups.get(x),
                                                                                           1)
        unneeded_cols = ['Trip ID', 'Agency Bill Code',
                         'Test Comment', 'Result Comment', 'Sample Report Limit',
                         'Chain of Custody', 'Cost Code', 'Test Number',
                         'CAS Number', 'Project Name',
                         'Sample Received Date', 'Method Description', 'Param Description',
                         'Dilution Factor', 'Batch Number', 'Replicate Number',
                         'Sample Detect Limit', 'Problem Identifier', 'Result Code',
                         'Sample Type', 'Project Comment', 'Sample Comment']

        state_lab_chem = state_lab_chem.drop(unneeded_cols, axis=1)
        state_lab_chem['ResultValueType'] = 'Actual'
        state_lab_chem['ResultStatusID'] = 'Final'
        state_lab_chem['ResultAnalyticalMethodContext'] = state_lab_chem['ResultAnalyticalMethodContext'].apply(
            lambda x: 'APHA' if x == 'SM' else 'USEPA', 1)
        state_lab_chem['inwqx'] = 0
        unitdict = {'MG-L': 'mg/l', 'UG-L': 'ug/l', 'NONE': 'None', 'UMHOS-CM': 'uS/cm'}
        state_lab_chem['ResultUnit'] = state_lab_chem['ResultUnit'].apply(lambda x: unitdict.get(x, x), 1)
        state_lab_chem['ResultDetecQuantLimitUnit'] = state_lab_chem['ResultUnit']
        state_lab_chem['resultid'] = state_lab_chem[['ActivityID', 'CharacteristicName']].apply(lambda x: x[0] + '-' + x[1],
                                                                                            1)
        self.state_lab_chem = state_lab_chem
        self.save_it(self.save_folder)
        return state_lab_chem

    def append_data(self):
        state_lab_chem = self.run_calcs()
        sdeact = table_to_pandas_dataframe(self.activities_table_name, field_names=['MonitoringLocationID', 'ActivityID'])
        sdechem = table_to_pandas_dataframe(self.chem_table_name, field_names=['MonitoringLocationID', 'ActivityID'])

        state_lab_chem['created_user'] = self.user
        state_lab_chem['last_edited_user'] = self.user
        state_lab_chem['created_date'] = pd.datetime.today()
        state_lab_chem['last_edited_date'] = pd.datetime.today()

        try:
            df = state_lab_chem[~state_lab_chem['ActivityID'].isin(sdeact['ActivityID'])]
            fieldnames = ['ActivityID', 'ProjectID', 'MonitoringLocationID', 'ActivityStartDate',
                          'ActivityStartTime', 'notes', 'personnel', 'created_user', 'created_date', 'last_edited_user',
                          'last_edited_date']

            for i in range(0, len(df), 500):
                j = i + 500
                if j > len(df):
                    j = len(df)
                subset = df.iloc[i:j]
                print("{:} to {:} complete".format(i, j))
                edit_table(subset, self.activities_table_name, fieldnames=fieldnames, enviro = self.enviro)
                print('success!')
        except Exception as err:
            print(err)
            print('fail!')
            pass

        try:
            df = state_lab_chem[~state_lab_chem['ActivityID'].isin(sdechem['ActivityID'])]
            fieldnames = ['ActivityID', 'MonitoringLocationID', 'ResultAnalyticalMethodContext', 'ResultAnalyticalMethodID',
                          'ResultSampleFraction',
                          'resultvalue', 'DetecQuantLimitMeasure', 'ResultDetecQuantLimitUnit', 'ResultUnit',
                          'AnalysisStartDate', 'ResultDetecQuantLimitType', 'ResultDetectionCondition',
                          'CharacteristicName',
                          'MethodSpeciation', 'characteristicgroup',
                          'inwqx', 'created_user', 'last_edited_user', 'created_date', 'last_edited_date', 'resultid']

            for i in range(0, len(df), 500):
                j = i + 500
                if j > len(df):
                    j = len(df)
                subset = df.iloc[i:j]
                print("{:} to {:} complete".format(i, j))
                edit_table(subset, self.chem_table_name, fieldnames = fieldnames, enviro = self.enviro)
                print('success!')
        except Exception as err:
            print(err)
            print('fail!')
            pass

    def pull_sde_stations(self):

        stations = table_to_pandas_dataframe(self.stations_table_name, field_names=['LocationID', 'QWNetworkName'])
        return stations

    def get_sample_matches(self):
        matches = pd.read_csv(self.sample_matches_file)
        matches = matches[['Station ID', 'Sample Number']].drop_duplicates()
        matches['Station ID'] = matches['Station ID'].apply(lambda x: "{:.0f}".format(x), 1)
        matches_dict = matches[['Sample Number', 'Station ID']].set_index(['Sample Number']).to_dict()['Station ID']
        return matches_dict

    def get_proj_match(self):
        stations = self.pull_sde_stations()

        projectmatch = stations[['LocationID', 'QWNetworkName']].set_index('LocationID').to_dict()['QWNetworkName']

        return projectmatch

    def ressampfr(self, x):
        if str(x).strip() == 'Water, Filtered':
            return 'Dissolved'
        else:
            return 'Total'

    def lssthn(self, x):
        if x[0] == '<':
            return "Below Reporting Limit"
        elif x[0] == '>':
            return "Above Operating Range"
        elif x[1] == 'U' and pd.isna(x[0]):
            return "Not Detected"
        else:
            return None

    def renamepar(self, df):

        x = df['Param Description']
        x = str(x).strip()
        y = None

        if x in self.param_explain.keys():
            z = self.param_explain.get(x)

        if " as " in x:
            z = x.split(' as ')[0]
            y = x.split(' as ')[1]
        else:
            z = x

        if str(z).strip() == 'Alkalinity':
            z = 'Alkalinity, total'

        if y == 'Calcium Carbonate':
            y = 'as CaCO3'
        elif y == 'Carbonate':
            y = 'as CO3'
        elif y == 'Nitrogen':
            y = 'as N'
        elif z == 'Total Phosphate' and pd.isna(y):
            z = 'Orthophosphate'
            y = 'as PO4'
        df['CharacteristicName'] = z
        df['MethodSpeciation'] = y
        return df

    def check_chems(self, df, char_schema):
        missing_chem = []
        for chem in df['CharacteristicName'].unique():
            if chem not in char_schema['Name'].values:
                print(chem)
                missing_chem.append(chem)
        return missing_chem

    def get_group_names(self):
        char_schema = pd.read_excel(self.schema_file_path, "CHARACTERISTIC")
        chemgroups = char_schema[['Name', 'Group Name']].set_index(['Name']).to_dict()['Group Name']
        return chemgroups

    def save_it(self, savefolder):
        self.state_lab_chem.to_csv("{:}/state_lab_to_sde_{:%Y%m%d}.csv".format(savefolder, pd.datetime.today()))

