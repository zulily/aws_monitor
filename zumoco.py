#!/usr/bin/env python
"""
zumoco worker
   Called by AWS Lambda to discover service instances
   which are then added to AWS CloudWatch and monitored.

   Copyright 2019 zulily, Inc.

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


import datetime
import json
import logging
from time import strftime

import boto3
from botocore import exceptions
import parsedatetime as pdt

Logger = logging.getLogger()
Logger.setLevel(logging.INFO)

CW_C = boto3.client('cloudwatch')
SNS_C = boto3.client('sns')
S3_C = boto3.client('s3')

# services zumoco has permission to describe
SERVICE_LIST = ['ec2', 'cloudwatch', 'lambda', 'sns', 'rds', 'autoscaling']

DEFS_PATH = 'monitordefs/'
TEAM_FILEPATH = DEFS_PATH + 'team.json'

DASHBOARD_MAX_WIDTH = 16
DASHBOARD_MAX_WIDGET = 50
MAX_SNS_MESSAGE = 1024 * 256

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


def load_instances(bucket, filename):
    """
    Load JSON instances from S3 file
    """
    try:
        obj = S3_C.get_object(Bucket=bucket, Key=filename)
        last_str = obj['Body'].read().decode('utf-8')
        insts = json.loads(last_str)
    except exceptions.ClientError as err:
        if err.response['Error']['Code'] == "NoSuchKey":
            Logger.warning('No file found:' + filename)
            insts = []
        else:
            raise

    return insts


def save_instances(inst_list, bucket, filename):
    """
    Save instances to S3 json
    """
    try:
        out = S3_C.put_object(Bucket=bucket, Key=filename,
                              Body=json.dumps(inst_list, ensure_ascii=False,
                                              default=dateconverter))
    except exceptions.ClientError as err:
        Logger.error('Issue writing file:' + filename + ':' + err)

    return out['ResponseMetadata']['HTTPStatusCode']

def dateconverter(date_obj):
    """
    Stringify datetime.datetime in a given instance
    """
    if isinstance(date_obj, datetime.datetime):
        return date_obj.__str__()


def determine_deltas(my_insts, my_last_insts):
    """
    Create lists of created and deleted instances since previous run.
    """

    if not my_last_insts:
        return None, my_insts
    else:
        idict = {a['myname']:a for a in my_insts}
        ldict = {a['myname']:a for a in my_last_insts}
        set_insts = set(tuple(idict.keys()))
        set_last_insts = set(tuple(ldict.keys()))
        newinstkeys = list(set_insts - set_last_insts)
        delinstkeys = list(set_last_insts - set_insts)
        newinsts = [idict[a] for a in newinstkeys]
        delinsts = [ldict[a] for a in delinstkeys]
        return delinsts, newinsts


def format_report(count, new_inst, del_inst, svc_info):
    """
    Given a service's new, deleted inst, return a string representation for email
    """
    needed = False
    body = ''
    if new_inst is not None and len(new_inst) > 0:
        needed = True
        body += '\n\n  New Instances: '
        for inst in new_inst:
            body += '\n    ' + inst['myname']
    else:
        body += '\n\n  No new instances.'
    if del_inst is not None and len(del_inst) > 0:
        needed = True
        body += '\n\n  Deleted Instances: '
        for inst in del_inst:
            body += '\n    ' + inst['myname']
    else:
        body += '\n\n  No deleted instances.'
    if needed:
        output = 'Service: ' + svc_info['Service']
        output += '\n  Total Instances: ' + str(count)
        output += '\n\n'
        return output + body

    return None


def send_report(report_text, svc_info, now_str):
    """
    Publish report to AWS SNS endpoint
    Note: publish takes a max of 256KB.
    """
    overage = len(report_text) - MAX_SNS_MESSAGE
    if overage > 0:
        report_text = report_text[:-overage - 20] + '\n<message truncated/>'
    resp = SNS_C.publish(TopicArn=svc_info['ReportARN'],
                         Message=report_text,
                         Subject='New/Deleted Instance Report for ' + now_str)
    return resp


def get_notify_targets(a_dest):
    """
    Return a dict of SNS alarm ARNs
    """
    topics = SNS_C.list_topics()['Topics']
    arns = [i['TopicArn'] for i in topics]
    return {a: a_dest[a] for a in a_dest if a_dest[a] in arns}


def get_service_instance_tag_value(inst, svc_client, svc_info, tag_name):
    """
    Retrieve given tag value from the given instance
    """
    # Requires another API call
    if svc_info['DiscoverTags']:
        cmd = 'svc_client.' + svc_info['DiscoverTags']
        if svc_info['DiscoverTagsInstParm']:
            cmd += 'inst["' + svc_info['DiscoverTagsInstParm'] + '"]'
        cmd += ')'
        inst = eval(cmd)
    # turn tag list into dictionary
    tagl = {i['Key']:i['Value'] for i in inst[svc_info['TagsKey']] if i['Value']}
    try:
        value = tagl[tag_name]
    except KeyError:
        value = ""
    return value


def create_friendly_name(instance, svc_client, svc_info):
    """
    Return the best name for alarm
    """
    Maxlen = 253
    friendly = None
    name = svc_info['AlarmPrefix'] + '_' + svc_info['Service']
    if svc_info['FriendlyName']:
        friendly = get_service_instance_tag_value(instance, svc_client, svc_info,
                                                  svc_info['FriendlyName'])
    if friendly:
        name += '_' + friendly[:Maxlen-(len(name)+len(svc_info['AlarmDimName']))]

    if svc_info['EnsureUniqueName'] or not friendly:
        name += '_' + instance[svc_info['AlarmDimName']]

    return name


def create_service_alarms(svc_inst, svc_client, svc_info):
    """
    Parse instances, creating alarms for each
    """
    alarms = svc_info['Alarms']
    alm_tgt = get_notify_targets(svc_info['AlarmDestinations'])
    for instance in svc_inst:
        for alarm in alarms:
            alarmname = instance['myname'] + '_' + alarm
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

    return get_service_alarms(svc_info['AlarmPrefix'], svc_info['Service'],
                              alarm_list=['All'])


def get_service_alarms(prefix, service, alarm_list):
    """
    Get all alarms for a given AlarmPrefix + service
    """
    alarms = []
    alarmprefix = prefix + '_' + service
    paginator = CW_C.get_paginator('describe_alarms')
    if alarm_list is not None:
        if alarm_list == ['All']:
            alarminst = alarmprefix
            for response in paginator.paginate(AlarmNamePrefix=alarminst):
                alarms.extend(response['MetricAlarms'])
        else:
            for inst in alarm_list:
                alarminst = alarmprefix + '_' + inst['myname']
                for response in paginator.paginate(AlarmNamePrefix=alarminst):
                    alarms.extend(response['MetricAlarms'])
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


def format_widget_props(svc_info, cht_name, chart, inst, alarms):
    """
    Helper to format AWS dashboard widget dictionary
    """
    metrics = []
    props = {}

    if chart['is_alarm']:
        arns = []
        for alarm in alarms:
            if alarm['MetricName'] in chart['metric_list']:
                if alarm['Dimensions'][0]['Value'] == inst[svc_info['AlarmDimName']]:
                    arns.append(alarm['AlarmArn'])
                    # currently AWS handles 1 alarm
                    break
        props['annotations'] = {'alarms' : arns}
    else:
        for mts in chart['metric_list']:
            metric = mts[:]
            metric.append(inst[svc_info['AlarmDimName']])
            metrics.append(metric)
        props['metrics'] = metrics
        avail_zone = eval('inst' + chart['avail'])
        props['region'] = avail_zone[:-1]
        props['stat'] = chart['stat']
    props['period'] = chart['period']
    props['view'] = chart['view']
    props['stacked'] = chart['stacked']
    props['title'] = cht_name
    return props


def build_dashboard_widgets(svc_inst, alarms, svc_info):
    """
    Parse instances, creating chart widgets
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
            cht_name = inst['myname'] + ' ' + cht
            widg['properties'] = format_widget_props(svc_info, cht_name,
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
    dashcount = int(wgtcount / DASHBOARD_MAX_WIDGET + 1)
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

def parse_service_response(svc_client, svc_info, response):
    """
    Handle paginated response from service
    """
    inst = []
    if svc_info['InstanceIterator2']:
        # Two levels of lists
        for tmp in response[svc_info['InstanceIterator1']]:
            for tmp2 in tmp[svc_info['InstanceIterator2']]:
                tmp2['myname'] = create_friendly_name(tmp2, svc_client, svc_info)
                inst.append(tmp2)
    elif svc_info['InstanceIterator1']:
        for tmp in response[svc_info['InstanceIterator1']]:
            tmp['myname'] = create_friendly_name(tmp, svc_client, svc_info)
            inst.append(tmp)
    else:
        for tmp in response:
            tmp['myname'] = create_friendly_name(tmp, svc_client, svc_info)
            inst.append(tmp)
    return inst


def get_service_instances(svc_client, svc_info):
    """
    Retrieve instances for the given service,
    Flattening AWS structure if necessary
    """
    instances = []
    paginator = svc_client.get_paginator(svc_info['DiscoverInstance'])
    if svc_info['InstanceFilters']:
        for response in paginator.paginate(Filters=svc_info['InstanceFilters']):
            instances.extend(parse_service_response(svc_client, svc_info, response))
    else:
        for response in paginator.paginate():
            instances.extend(parse_service_response(svc_client, svc_info, response))

    return instances



def main(event, context):
    """
    Main functionality
    """
    all_widgets = []
    cons = pdt.Constants()
    cons.YearParseStyle = 0
    pdtcal = pdt.Calendar(cons)
    now_tm = pdtcal.parse("now")
    now_str = strftime('%c', now_tm[0])

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
            #   Get new instances.
            instances = get_service_instances(svc_client, svc_info)
            instfile = svc_info['Service'] + '_' + svc_info['S3Suffix'] + '.json'
            # Get old instances
            old_inst = load_instances(team_info['Bucket'], instfile)
            # Determine what's new and deleted.
            del_inst, new_inst = determine_deltas(list(instances), old_inst)
            #   Cleanup any old instance alarms.
            delete_service_alarms(get_service_alarms(svc_info['AlarmPrefix'],
                                                     svc_info['Service'],
                                                     alarm_list=del_inst))
            http_status = save_instances(instances, team_info['Bucket'],
                                         instfile)
            if http_status != 200:
                Logger.error('Unable to write instances file:' + instfile)

            report_text = format_report(len(instances), new_inst, del_inst, svc_info)
            if team_info['SendStatusUpdates'] and report_text:
                send_report(report_text, svc_info, now_str)

            #   Create instance alarms for new instances.
            alarms = create_service_alarms(new_inst, svc_client, svc_info)

            dash_j = build_dashboard_widgets(instances, alarms, svc_info)
            all_widgets.extend(dash_j)

            #   If service dashboard is requested, create one.
            if svc_info['CreateServiceDashboard']:
                name = svc_info['AlarmPrefix'] + '_' + svc_info['Service']
                name += '_' + svc_info['S3Suffix']
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
