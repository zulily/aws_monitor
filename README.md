# Dynamic Monitoring of AWS

Keeping track of your instances in AWS is quite a task.  This tool (zumoco, for zulily monitoring collector), run routinely from AWS Lambda, will detect your instances, add CloudWatch alerting for each, and create CloudWatch dashboards based on your preferences.

## Setup
There are a few things you need to do to set this up for yourself (see details below):  
 
  - Create the AWS Simple Notification Service (SNS) topics/subscriptions for notifying teams based on alert severity.
  - Customize the JSON templates in the `monitordefs` directory to match the services you want to monitor.
  - Package and deploy the lambda function to AWS.

### Create AWS SNS topics/subscriptions
AWS uses SNS to handle notifications of AWS CloudWatch alerts. zumoco uses the Amazon Resource Name (ARN) for a given SNS topic (connected to a notification endpoint) when creating a CloudWatch alert.  Various SNS topic/subscriptions can be created as follows:

 - Create a PagerDuty integration for SNS following the process here: [link](https://www.pagerduty.com/docs/guides/aws-cloudwatch-integration-guide/)  (ARN is available following Step 4. of the "AWS SNS Console" section.)
 - Create a Slack integration for SNS by creating another AWS Lambda function, which pushes SNS events to the Slack Chat server. The description of the AWS Lambda template is found here: [link](https://aws.amazon.com/blogs/aws/new-slack-integration-blueprints-for-aws-lambda/).
 - Create a hipchat integration by creating another AWS Lambda function, as provided here: [link](https://github.com/zulily/aws_monitor/tree/master/sns_integrations).  Note: the `tests/zumoco_test.py` test file requires an SNS topic to create alarms; replace the appropriate `AlarmDestinations` values with your SNS topic in order to run the tests.
 - Create an email integration, using the AWS process here: [link](http://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/US_SetupSNS.html)

### Customize the JSON templates

* Edit `team.json` to modify:

 - `Team` : Set to your team's name.
 - `CreateTeamDashboard` : Set to false if you don't want a dashboard set with all metric alarms.
 - `MonitorDefs` list : Change to reference only the services' files on which you plan to alert.

* Copy each service you want to monitor (e.g., `ec2_TeamFoo.json`) to a new filename (referencing it in the `team.json` `MonitorDefs` list.)  In the new file, modify:

 - `InstanceFilters` : If your instances have names, add `tag:Name` key's values as you likely want to restrict monitoring (and dashboard generation) to a subset of instances (less than 1k total, per AWS API docs).  (If you do this, you also should to change the `AlarmPrefix` to keep dashboards, etc., separate.) Example:
	 - `"Filters=[{'Name':'tag:Name', 'Values':['hadoop*']},{'Name':'instance-state-name', 'Values':['running']}]"`
 - `AlarmDestinations` : Modify to include all SNS topic/subscription alarm destinations you created in the previous section.
 - `CreateServiceDashboard` : Set to false if you don't want a dashboard set with all metric alarms for the given service.
 - `AlarmPrefix` : Use this string to name all (filtered) instance alerts of the given service.
 - `Alarms` section:  (Add/remove/change [metrics](http://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CW_Support_For_AWS.html) in this dictionary as necessary).
	 - `AlarmAction` : Set this to the appropriate `AlarmDestination` name.
	 - `send_ok` : Set this boolean to `false` if you don't want `OKAction` messages sent to the same `AlarmDestination` as the `AlarmAction`.
	 -  `Period` : Adjust based on basic/detailed monitoring, etc.
	 -  `Threshold` : Adjust based on preferences.
	- `Charts` section:  (Add/remove/change [charts](http://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/CloudWatch-Dashboard-Body-Structure.html) in this dictionary as necessary).
		- `ch_type` : "Metric" is currently supported for auto-generation.
		- `is_alarm` : Boolean determining whether chart is an alarm chart (requiring ARN from an alarm) or a metrics chart without alarm values shown.
		- `avail` : String used to select availability zone in instance JSON (varies by service instance).
		- `metric_list` : List of metrics or alarm to be charted, following [charts](http://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/CloudWatch-Dashboard-Body-Structure.html) definition.
		- `view` : Note: `singleValue` charts are half the width of `timeSeries` charts.

The packaging step will deploy everything in the monitordefs directory to the Lambda zip file (so you may wish to remove templates/files you don't use).
	
	
### Package and deploy the lambda function

1. Edit `vars.sh` to set the rate for the lambda function to run inside your VPC.
1. Run `./deploy_lambda_function.sh`.  This will:

* Package up the script with its dependencies into the zip format that AWS Lambda expects (as defined in `package.sh`).
* Interact with the AWS API to set up the lambda function with the things it needs (as defined in `deployscripts/setup_lambda.py`):
  * Creates an IAM role for the lambda function to use.  Review the json files in the `deployscripts` directory to see the permissions 
  required.
  * Uploads the zip file from the previous step to create a Lambda function (possibly publishing a new version if the function 
  already exists).

 
