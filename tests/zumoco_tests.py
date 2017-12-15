#!/usr/bin/env python
"""
   Tests for zumoco.py
   Called via nosetests tests/zumoco_tests.py
"""

# Global imports
import unittest

import boto3

from pprint import pprint

# Local imports
import zumoco


class TestZumoco(unittest.TestCase):
    """
    Standard test class, for all zumoco functions
    """
    @staticmethod
    def svcinfo_helper():
        """
        provide minimal monitordef for test
        """
        # Assume instances aren't named.
        # Add {'Name':'tag:Name', 'Values':['*']}, to Filters to get named instances.
        return {
            'InstanceFilters' : [
                    {
                            'Name':'instance-state-name', 
                            'Values':['running']
                    }
            ],
            'DiscoverInstance' : 'describe_instances',
            'Service' : 'ec2',
            'InstanceIterator1' : 'Reservations',
            'InstanceIterator2' : 'Instances',
            'AlarmDimName' : 'InstanceId',
            'AlarmPrefix' : 'zumocotest',
            'Alarms' : {
                'CPUUtilization': {
                    'AlarmDescription' : 'Alarm for EC2 CPUUtilization Metric',
                    'AlarmAction' : 'critical',
                    'send_ok' : True,
                    'ComparisonOperator' : 'GreaterThanThreshold',
                    'EvaluationPeriods' : 2,
                    'Statistic' : 'Average',
                    'MetricName' : 'CPUUtilization',
                    'Namespace' : 'AWS/EC2',
                    'Period' : 300,
                    'Threshold' : 60
                },
                'DiskReadBytes': {
                    'AlarmDescription' : 'Alarm for EC2 DiskReadBytes Metric',
                    'AlarmAction' : 'warning',
                    'send_ok' : True,
                    'ComparisonOperator' : 'GreaterThanThreshold',
                    'EvaluationPeriods' : 2,
                    'MetricName': 'DiskReadBytes',
                    'Statistic' : 'Average',
                    'Namespace' : 'AWS/EC2',
                    'Period' : 300,
                    'Threshold' : 3000000000
                },
                'DiskWriteBytes': {
                    'AlarmDescription' : 'Alarm for EC2 DiskWriteBytes Metric',
                    'AlarmAction' : 'warning',
                    'send_ok' : True,
                    'ComparisonOperator' : 'GreaterThanThreshold',
                    'EvaluationPeriods' : 2,
                    'MetricName': 'DiskWriteBytes',
                    'Statistic' : 'Average',
                    'Namespace' : 'AWS/EC2',
                    'Period' : 300,
                    'Threshold' : 1000000000
                },
                'NetworkIn': {
                    'AlarmDescription' : 'Alarm for EC2 NetworkIn Metric',
                    'AlarmAction' : 'critical',
                    'send_ok' : True,
                    'ComparisonOperator' : 'GreaterThanThreshold',
                    'EvaluationPeriods' : 2,
                    'MetricName': 'NetworkIn',
                    'Statistic' : 'Average',
                    'Namespace' : 'AWS/EC2',
                    'Period' : 300,
                    'Threshold' : 450000000
                },
                'NetworkOut': {
                    'AlarmDescription' : 'Alarm for EC2 NetworkOut Metric',
                    'AlarmAction' : 'critical',
                    'send_ok' : True,
                    'ComparisonOperator' : 'GreaterThanThreshold',
                    'EvaluationPeriods' : 2,
                    'MetricName': 'NetworkOut',
                    'Statistic' : 'Average',
                    'Namespace' : 'AWS/EC2',
                    'Period' : 300,
                    'Threshold' : 450000000
                },
                'StatusCheckFailed': {
                    'AlarmDescription' : 'Alarm for EC2 StatusCheckFailed Metric',
                    'AlarmAction' : 'critical',
                    'send_ok' : True,
                    'ComparisonOperator' : 'GreaterThanOrEqualToThreshold',
                    'EvaluationPeriods' : 2,
                    'MetricName': 'StatusCheckFailed',
                    'Statistic' : 'Maximum',
                    'Namespace' : 'AWS/EC2',
                    'Period' : 300,
                    'Threshold' : 1
                }
            },
            'AlarmDestinations' : {
                'info' : None,
                'warning' : 'arn:aws:sns:us-east-1:445473265646:infra_warning_hipchat',
                'critical' : 'arn:aws:sns:us-east-1:445473265646:infra_warning_hipchat'
            },
            'Charts' : {
                'StatusCheckFailed': {
                    'ch_type' : 'metric',
                    'is_alarm' : True,
                    'metric_list' : ['StatusCheckFailed'],
                    'period' : 300,
                    'view' : 'singleValue',
                    'stacked' : False
                },
                'CPU': {
                    'ch_type' : 'metric',
                    'is_alarm' : True,
                    'metric_list' : ['CPUUtilization'],
                    'period' : 300,
                    'view' : 'timeSeries',
                    'stacked' : False
                },
                'Network': {
                    'ch_type' : 'metric',
                    'is_alarm' : False,
                    'avail' : "['Placement']['AvailabilityZone']",
                    'metric_list' : [['AWS/EC2', 'NetworkIn', 'InstanceId'],
                                     ['AWS/EC2', 'NetworkOut', 'InstanceId']],
                    'period' : 300,
                    'stat' : 'Average',
                    'stacked' : True,
                    'view' : 'timeSeries'
                },
                'Disk': {
                    'ch_type' : 'metric',
                    'is_alarm' : False,
                    'avail' : "['Placement']['AvailabilityZone']",
                    'metric_list' : [['AWS/EC2', 'DiskReadBytes', 'InstanceId'],
                                     ['AWS/EC2', 'DiskWriteBytes', 'InstanceId']],
                    'period' : 300,
                    'stat' : 'Average',
                    'stacked' : True,
                    'view' : 'timeSeries'
                }
            }
        }

    def setUp(self):
        """
        set up if needed
        """
        print ""


    def tearDown(self):
        """
        tear down!
        """
        print ""


    def test_load_monitor_file(self):
        """
        Test the method used for loading the team and monitor json
        """
        team_info = zumoco.load_monitor_file(zumoco.TEAM_FILEPATH)
        self.assertEqual(len(team_info), 6)
        self.assertGreaterEqual(len(team_info['MonitorDefs']), 1)
        monitorpath = zumoco.DEFS_PATH + team_info['MonitorDefs'][0]
        svc_info = zumoco.load_monitor_file(monitorpath)
        self.assertGreaterEqual(len(svc_info), 6)
        self.assertGreaterEqual(len(svc_info['Alarms']), 2)

    def test_load_bad_monitor_file(self):
        """
        Test the method used for load malformed team and monitor json
        """
        badpath = zumoco.DEFS_PATH + 'bad_team.json'
        team_info = zumoco.load_monitor_file(badpath)
        self.assertEqual(len(team_info), 0)

    def test_get_service_instances(self):
        """
        Test the method used for loading the service instance
        """
        test_info = self.svcinfo_helper()
        test_client = boto3.client(test_info['Service'])
        instances = zumoco.get_service_instances(test_client, test_info)
        self.assertGreaterEqual(len(instances), 2)

    def test_create_service_alarms(self):
        """
        Test the method used for creating cloudwatch alarms
        """
        test_info = self.svcinfo_helper()
        test_client = boto3.client(test_info['Service'])
        instances = zumoco.get_service_instances(test_client, test_info)
        test_alarms = zumoco.create_service_alarms(instances, test_info)
        self.assertEqual(len(test_alarms), len(test_info['Alarms'])*len(instances))
        self.assertGreaterEqual(len(test_alarms), 2)

    def test_get_delete_service_alarms(self):
        """
        Test the method used for retrieving and deleting cloudwatch alarms
        """
        test_info = self.svcinfo_helper()
        test_alarms = zumoco.get_service_alarms(test_info['AlarmPrefix'], test_info['Service'])
        self.assertGreaterEqual(len(test_alarms), len(test_info['Alarms']))
        zumoco.delete_service_alarms(test_alarms)
        test_alarms = zumoco.get_service_alarms(test_info['AlarmPrefix'], test_info['Service'])
        self.assertEqual(len(test_alarms), 0)

    def test_build_gen_del_dashboard(self):
        """
        Test the methods used for creating and deleting a cloudwatch dashboard
        """
        test_info = self.svcinfo_helper()
        test_client = boto3.client(test_info['Service'])
        instances = zumoco.get_service_instances(test_client, test_info)
        test_alarms = zumoco.create_service_alarms(instances, test_info)
        test_widg = zumoco.build_dashboard_widgets(instances, test_alarms, test_info)
        self.assertEqual(len(test_widg), len(test_info['Charts'])*len(instances))
        chart_j = {'widgets' : test_widg}
        name = test_info['AlarmPrefix'] + '_' + test_info['Service']
        test_dashboard = zumoco.generate_dashboard(name, chart_j)
        self.assertEqual(len(test_dashboard), 1)
        zumoco.delete_dashboards(test_dashboard)
        test_dashboard = zumoco.get_dashboards(test_info['AlarmPrefix'])
        self.assertEqual(len(test_dashboard), 0)

    def test_custom_gen_del_dashboards(self):
        """
        Test creating multiple trivial cloudwatch dashboards
        """
        widgets = []
        x_val = 0
        y_val = 0
        width = 6
        height = 4
        for dcount in range(0, 151):
            wdg = {}
            props = {}
            wdg['type'] = 'text'
            wdg['x'] = x_val
            wdg['y'] = y_val
            wdg['height'] = height
            wdg['width'] = width
            props['markdown'] = 'Widget #' + str(dcount)
            wdg['properties'] = props
            widgets.append(wdg)
            x_val += wdg['width']
            if x_val > 16:
                x_val = 0
                y_val += height

        test_info = self.svcinfo_helper()
        chart_j = {'widgets' : widgets}
        name = test_info['AlarmPrefix'] + '_' + test_info['Service']
        test_dashboard = zumoco.generate_dashboard(name, chart_j)
        self.assertEqual(len(test_dashboard), 4)
        zumoco.delete_dashboards(test_dashboard)
        test_dashboard = zumoco.get_dashboards(name)
        self.assertEqual(len(test_dashboard), 0)

    def test_notify_targets(self):
        """
        Test the method to return AlarmDestinations
        """
        test_info = self.svcinfo_helper()
        targets = zumoco.get_notify_targets(test_info['AlarmDestinations'])
        self.assertEqual(len(targets), len(test_info['AlarmDestinations'])-1)
