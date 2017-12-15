#!/usr/bin/env python
"""
zumoco worker
   Called by AWS Lambda to discover service instances
   which are then added to AWS CloudWatch and monitored.

   Copyright 2017 zulily, Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""


import json
import logging

import boto3
from botocore import exceptions

Logger = logging.getLogger()
Logger.setLevel(logging.INFO)

CW_C = boto3.client('cloudwatch')
SNS_C = boto3.client('sns')

# services zumoco has permission to describe
SERVICE_LIST = ['ec2', 'cloudwatch', 'lambda', 'sns', 'rds', 'autoscaling']

DEFS_PATH = 'monitordefs/'
TEAM_FILEPATH = DEFS_PATH + 'team.json'

DASHBOARD_MAX_WIDTH = 16
DASHBOARD_MAX_WIDGET = 50

def load_monitor_file(file_name):
    """
    Load team JSON
    """
    try:
        with open(file_name, 'r') as monfile:
            mydict = json.load(monfile)
    except IOError as error:
        mydict = ""
        Logger.warning('Failed to load ' + file_name)
        Logger.critical('Critical Error: ' + str(error))
    return mydict


def get_notify_targets(a_dest):
    """
    Return a dict of SNS alarm ARNs
    """
    topics = SNS_C.list_topics()['Topics']
    arns = [i['TopicArn'] for i in topics]
    return {a: a_dest[a] for a in a_dest if a_dest[a] in arns}


def create_service_alarms(svc_inst, svc_info):
    """
    Parse instances, creating alarms for each
    """
    alarms = svc_info['Alarms']
    alm_tgt = get_notify_targets(svc_info['AlarmDestinations'])
    for instance in svc_inst:
        name = svc_info['AlarmPrefix'] + '_' + svc_info['Service']
        name += '_' + instance[svc_info['AlarmDimName']]
        for alarm in alarms:
            alarmname = name + '_' + alarm
            try:
                if alarms[alarm]['send_ok']:
                    CW_C.put_metric_alarm(AlarmName=alarmname,
                                          MetricName=alarms[alarm]['MetricName'],
                                          Namespace=alarms[alarm]['Namespace'],
                                          AlarmDescription=alarms[alarm]['AlarmDescription'],
                                          Statistic=alarms[alarm]['Statistic'],
                                          Period=alarms[alarm]['Period'],
                                          Threshold=alarms[alarm]['Threshold'],
                                          ComparisonOperator=alarms[alarm]['ComparisonOperator'],
                                          EvaluationPeriods=alarms[alarm]['EvaluationPeriods'],
                                          AlarmActions=[alm_tgt[alarms[alarm]['AlarmAction']]],
                                          OKActions=[alm_tgt[alarms[alarm]['AlarmAction']]],
                                          Dimensions=[{'Name':svc_info['AlarmDimName'],
                                                       'Value':instance[svc_info['AlarmDimName']]}])
                else:
                    CW_C.put_metric_alarm(AlarmName=alarmname,
                                          MetricName=alarms[alarm]['MetricName'],
                                          Namespace=alarms[alarm]['Namespace'],
                                          AlarmDescription=alarms[alarm]['AlarmDescription'],
                                          Statistic=alarms[alarm]['Statistic'],
                                          Period=alarms[alarm]['Period'],
                                          Threshold=alarms[alarm]['Threshold'],
                                          ComparisonOperator=alarms[alarm]['ComparisonOperator'],
                                          EvaluationPeriods=alarms[alarm]['EvaluationPeriods'],
                                          AlarmActions=[alm_tgt[alarms[alarm]['AlarmAction']]],
                                          Dimensions=[{'Name':svc_info['AlarmDimName'],
                                                       'Value':instance[svc_info['AlarmDimName']]}])

            except KeyError:
                Logger.warning('Failed to create alarm: ' + alarmname)
                Logger.warning('Ensure valid AlarmDestinations / AlarmDimName')
                Logger.warning('in monitor definitions:' + svc_info['Service'])


    return get_service_alarms(svc_info['AlarmPrefix'], svc_info['Service'])

def get_service_alarms(prefix, service):
    """
    Get all alarms for a given AlarmPrefix + service
    """
    alarms = []
    alarmprefix = prefix + '_' + service
    paginator = CW_C.get_paginator('describe_alarms')
    for response in paginator.paginate(AlarmNamePrefix=alarmprefix):
        alarms.extend(response['MetricAlarms'])
        pass
    return alarms

def delete_service_alarms(alarm_list):
    """
    Delete all alarms passed to the function
    """
    alarmnames = []
    for alarm in alarm_list:
        alarmnames.append(alarm['AlarmName'])
        # limit of 100 for delete
        if len(alarmnames) > 90:
            CW_C.delete_alarms(AlarmNames=alarmnames)
            alarmnames = []
    if alarmnames:
        CW_C.delete_alarms(AlarmNames=alarmnames)

def format_widget_props(inst_name, cht_name, chart, inst, alarms):
    """
    Helper to format AWS dashboard widget dictionary
    """
    metrics = []
    props = {}

    if chart['is_alarm']:
        arns = []
        for alarm in alarms:
            if alarm['MetricName'] in chart['metric_list']:
                if alarm['Dimensions'][0]['Value'] == inst_name:
                    arns.append(alarm['AlarmArn'])
                    # currently AWS handles 1 alarm
                    break
        props['annotations'] = {'alarms' : arns}
    else:
        for mts in chart['metric_list']:
            metric = mts[:]
            metric.append(inst_name)
            metrics.append(metric)
        props['metrics'] = metrics
        avail_zone = eval('inst' + chart['avail'])
        props['region'] = avail_zone[:-1]
        props['stat'] = chart['stat']
    props['period'] = chart['period']
    props['view'] = chart['view']
    props['stacked'] = chart['stacked']
    props['title'] = inst_name + ' ' + cht_name
    return props

def build_dashboard_widgets(svc_inst, alarms, svc_info):
    """
    Parse instances and/or alarms, creating chart widgets
    """

    widgets = []
    x_val = 0
    y_val = 0
    width = 6
    height = 4
    chts = svc_info['Charts']
    for inst in svc_inst:
        for cht in chts:
            # build a chart widget
            widg = {}
            inst_name = inst[svc_info['AlarmDimName']]
            widg['properties'] = format_widget_props(inst_name, cht,
                                                     chts[cht], inst, alarms)
            widg['type'] = chts[cht]['ch_type']

            # position graph
            widg['x'] = x_val
            widg['y'] = y_val
            widg['height'] = height
            widg['width'] = width

            # go small if singleValue chart
            if widg['properties']['view'] == 'singleValue':
                widg['width'] /= 2
            widgets.append(widg)

            # wrap to next line, if necessary
            x_val += widg['width']
            if x_val > DASHBOARD_MAX_WIDTH:
                x_val = 0
                y_val += height

    return widgets

def generate_dashboard(name, chart_j):
    """
    Given chart widgets, create a dashboard
    """
    wgtcount = len(chart_j['widgets'])
    dashcount = wgtcount / DASHBOARD_MAX_WIDGET + 1
    for dash in range(0, dashcount):
        dname = name + '_' + str(dash+1)
        widglist = chart_j['widgets'][dash * DASHBOARD_MAX_WIDGET: \
                                      min(dash * DASHBOARD_MAX_WIDGET + wgtcount,
                                          (dash+1) * DASHBOARD_MAX_WIDGET)]
        dwidgets = {'widgets' : widglist}
        CW_C.put_dashboard(DashboardName=dname, DashboardBody=json.dumps(dwidgets))
        wgtcount -= DASHBOARD_MAX_WIDGET

    return get_dashboards(name)


def get_dashboards(prefix):
    """
    Get Cloudwatch dashboards for a given prefix
    """
    dashboards = CW_C.list_dashboards(DashboardNamePrefix=prefix)
    return dashboards['DashboardEntries']

def delete_dashboards(dashboard_list):
    """
    Delete all dashboards passed to the function
    """
    dashboardnames = []
    for dashboard in dashboard_list:
        dashboardnames.append(dashboard['DashboardName'])
    if dashboardnames:
        CW_C.delete_dashboards(DashboardNames=dashboardnames)

def parse_service_response(response, inst_iter1, inst_iter2):
    """
    Handle paginated response from service
    """
    inst = []
    if inst_iter2:
        # Two levels of lists
        for tmp in response[inst_iter1]:
            for tmp2 in tmp[inst_iter2]:
                inst.append(tmp2)
    elif inst_iter1:
        for tmp in response[inst_iter1]:
            inst.append(tmp)
    else:
        inst = response
        pass
    return inst


def get_service_instances(svc_client, svc_info):
    """
    Retrieve instances for the given service,
    Flattening AWS structure if necessary
    """
    instances = []
    responses = []
    paginator = svc_client.get_paginator(svc_info['DiscoverInstance'])
    if svc_info['InstanceFilters']:
        for response in paginator.paginate(Filters=svc_info['InstanceFilters']):
            instances.extend(parse_service_response(response, svc_info['InstanceIterator1'],
                                                    svc_info['InstanceIterator2']))
    else:
        for response in paginator.paginate():
            instances.extend(parse_service_response(response, svc_info['InstanceIterator1'],
                                                    svc_info['InstanceIterator2']))
    return instances 



def main(event, context):
    """
    Main functionality
    """
    all_widgets = []
    ##### PROGRAM FLOW #####
    # Load team file
    team_info = load_monitor_file(TEAM_FILEPATH)

    # For each service file in MonitorDefs,
    for svc in team_info['MonitorDefs']:

        #   Load service file
        svc_info = load_monitor_file(DEFS_PATH + svc)

        #   Ensure API exists for service
        try:
            svc_client = boto3.client(svc_info['Service'])
        except exceptions.UnknownServiceError:
            Logger.critical('Service unknown to AWS API:' + svc_info['Service'])

        if svc_info['Service'] in SERVICE_LIST:
            #   Get instances.
            instances = get_service_instances(svc_client, svc_info)
            #   Cleanup any old instance alarms.
            delete_service_alarms(get_service_alarms(svc_info['AlarmPrefix'], svc_info['Service']))
            #   Create instance alarms for all instances.
            alarms = create_service_alarms(instances, svc_info)

            dash_j = build_dashboard_widgets(instances, alarms, svc_info)
            all_widgets.extend(dash_j)

            #   If service dashboard is requested, create one.
            if svc_info['CreateServiceDashboard']:
                name = svc_info['AlarmPrefix'] + '_' + svc_info['Service']
                chart_j = {'widgets' : dash_j}
                delete_dashboards(get_dashboards(name))
                generate_dashboard(name, chart_j)
        else:
            Logger.warning('No permissions for listing instances. Service: ')
            Logger.warning(svc_info['Service'])
    # If team dashboard is requested, create one
    if team_info['CreateTeamDashboard']:
        name = svc_info['AlarmPrefix'] + '_' + team_info['Team']
        chart_j = {'widgets' : all_widgets}
        delete_dashboards(get_dashboards(name))
        generate_dashboard(name, chart_j)


#main('foo', 'bar')
