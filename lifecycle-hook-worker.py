#!/usr/bin/env python

import boto3
import sys
import argparse
import ast
import urllib2
from subprocess import call
import time
from datetime import datetime

def sqs_consumer(qname):
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=qname)
    client = boto3.client('sqs')
    message = client.receive_message(QueueUrl=queue.url, MaxNumberOfMessages=1, WaitTimeSeconds=20)
    if message.get('Messages'):
       m = message.get('Messages')[0]
       body = ast.literal_eval(m['Body'])
       receipt_handle = m['ReceiptHandle']
       response = client.delete_message(QueueUrl=queue.url, ReceiptHandle=receipt_handle)
    else:
       body = {'timeout': True, 'Event': False}
    return(body)

def get_ec2instanceid():
    # curl http://169.254.169.254/latest/meta-data/instance-id
    response = urllib2.urlopen('http://169.254.169.254/latest/meta-data/instance-id')
    instanceid = response.read()
    return instanceid

def main():
    parser = argparse.ArgumentParser(description='SQS Lifecycle hook consumer and trigger')
    parser.add_argument('-q', '--queue', required=True,
                        help="Queue resource.")
    parser.add_argument('-s', '--state', action='store', choices=['LAUNCHING','TERMINATING'], required=True,
                        help='Indicates if the consumer is waiting for LAUNCHING or TERMINATING state')
    parser.add_argument('-g', '--group', required=True,
                        help='Auto Scaling Group Name')
    parser.add_argument('-H', '--hookName', required=True,
                        help='Life Cycle Hook Name')
    parser.add_argument('-e', '--execute', required=True,
                        help="The filepath of the triggered script")
    parser.add_argument('-w', '--wait', default=60, type=int,
                        help="Time between query loops in seconds (default: 60)")

    arg = parser.parse_args()

    if arg.state == "LAUNCHING":
       state = "autoscaling:EC2_INSTANCE_TERMINATING"
    elif arg.state == "TERMINATING":
       state = "autoscaling:EC2_INSTANCE_LAUNCHING"

    ec2instanceid = get_ec2instanceid()
    print ("%s Listening for %s SQS messages using long polling") % (datetime.now().strftime('%H:%M:%S %D'), ec2instanceid)

    while 1:
       sqs_msg = sqs_consumer(arg.queue)
       if sqs_msg['Event'] == "autoscaling:TEST_NOTIFICATION":
          print ("%s Tests message consumed") % datetime.now().strftime('%H:%M:%S %D')
       elif sqs_msg['timeout']:
          print ("%s There are no messages in the queue. Sleeping and trying again") % datetime.now().strftime('%H:%M:%S %D')
       elif (sqs_msg['Event'] == state) and (sqs_msg['EC2InstanceId'] == ec2instanceid):
          print "%s %s hook message received" % (datetime.now().strftime('%H:%M:%S %D'), arg.state)
          print "%s Executing filepath" % datetime.now().strftime('%H:%M:%S %D')
          call(["uname", "-a"])
          print "%s Completing lifecyle action" % datetime.now().strftime('%H:%M:%S %D')
          as_client = boto3.client('autoscaling')
          response = as_client.complete_lifecycle_action(
             LifecycleHookName=arg.hookName,
             AutoScalingGroupName=arg.group,
             LifecycleActionToken=sqs_msg['LifecycleActionToken'],
             LivecycleActionResult='CONTINUE',
             InstanceID=ec2instanceid
          )
       time.sleep(arg.wait)

if __name__ == '__main__':
    sys.exit(main())