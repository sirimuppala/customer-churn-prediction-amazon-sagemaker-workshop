#!/usr/bin/pythono

## Deploy a pretrained model as part of the lifecycle configuration


import os
import boto3
import re
import json
from sagemaker import get_execution_role, session


region = boto3.Session().region_name

role = get_execution_role()
print("RoleArn: {}".format(role))

# You can modify the bucket to be your own, but make sure the role you chose for this notebook
# has s3:PutObject permissions. This is the bucket into which the data will be captured
bucket =  session.Session(boto3.Session()).default_bucket()
print("Recommendations Bucket: {}".format(bucket))
prefix = 'sagemaker/Recommendations-ModelMonitor'

data_capture_prefix = '{}/datacapture'.format(prefix)
s3_capture_upload_path = 's3://{}/{}'.format(bucket, data_capture_prefix)
reports_prefix = '{}/reports'.format(prefix)
s3_report_path = 's3://{}/{}'.format(bucket,reports_prefix)
code_prefix = '{}/code'.format(prefix)
s3_code_preprocessor_uri = 's3://{}/{}/{}'.format(bucket,code_prefix, 'preprocessor.py')
s3_code_postprocessor_uri = 's3://{}/{}/{}'.format(bucket,code_prefix, 'postprocessor.py')

print("Capture path: {}".format(s3_capture_upload_path))
print("Report path: {}".format(s3_report_path))
print("Preproc Code path: {}".format(s3_code_preprocessor_uri))
print("Postproc Code path: {}".format(s3_code_postprocessor_uri))

sm_client = boto3.client('sagemaker')

LOCAL_MODELS_DIR='models'
LOCAL_DATA_DIR='data'

MOVIE_RECOMMENDATION_MODEL='movie-rec-all-features.tar.gz'
MUSIC_RECOMMENDATION_MODEL='music-rec-kiran.tar.gz'

MOVIE_RECOMMENDATION_TRAIN_DATA='movie_train.csv'

MOVIE_RECOMMENDATION_TEST_DATA='movie_test.csv'
MUSIC_RECOMMENDATION_TEST_DATA='music_test.csv'

##Copy the model to S3
model_name = MOVIE_RECOMMENDATION_MODEL

key = prefix + "/" + model_name
with open(LOCAL_MODELS_DIR+'/'+model_name, 'rb') as file_obj:
    print("Uploading ", file_obj , " to bucket ",bucket, " as " , key)
    boto3.Session().resource('s3').Bucket(bucket).Object(key).upload_fileobj(file_obj)

from sagemaker.amazon.amazon_estimator import get_image_uri
container = get_image_uri(boto3.Session().region_name, 'xgboost', '0.90-1')

from time import gmtime, strftime

model_name = "MoviePredictions-EndpointDataCaptureModel-" + strftime("%Y-%m-%d-%H-%M-%S", gmtime())

sm_client = boto3.client('sagemaker')

model_url = 'https://{}.s3-{}.amazonaws.com/{}/{}'.format(bucket, region, prefix,MOVIE_RECOMMENDATION_MODEL)

print (model_url)

primary_container = {
    'Image': container,
    'ModelDataUrl': model_url,
}

create_model_response = sm_client.create_model(
    ModelName = model_name,
    ExecutionRoleArn = role,
    PrimaryContainer = primary_container)

print(create_model_response['ModelArn'])


data_capture_sub_folder = "datacapture-xgboost-movie-recommendations"
s3_capture_upload_path = 's3://{}/{}'.format(bucket, data_capture_sub_folder)

print("Capture path:"+ s3_capture_upload_path)

data_capture_configuration = {
    "EnableCapture": True, # flag turns data capture on and off
    "InitialSamplingPercentage": 90, # sampling rate to capture data. max is 100%
    "DestinationS3Uri": s3_capture_upload_path, # s3 location where captured data is saved
    "CaptureOptions": [
        {
            "CaptureMode": "Output" # The type of capture this option enables. Values can be: [Output/Input]
        },
        {
            "CaptureMode": "Input" # The type of capture this option enables. Values can be: [Output/Input]
        }
    ],
    "CaptureContentTypeHeader": {
       "CsvContentTypes": ["text/csv"], # headers which should signal to decode the payload into CSV format
       "JsonContentTypes": ["application/json"] # headers which should signal to decode the payload into JSON format
     }
}

endpoint_config_name = 'XGBoost-MovieRec-DataCaptureEndpointConfig-' + strftime("%Y-%m-%d-%H-%M-%S", gmtime())
print(endpoint_config_name)
create_endpoint_config_response = sm_client.create_endpoint_config(
    EndpointConfigName = endpoint_config_name,
    ProductionVariants=[{
        'InstanceType':'ml.m5.xlarge',
        'InitialInstanceCount':1,
        'InitialVariantWeight':1,
        'ModelName':model_name,
        'VariantName':'AllTrafficVariant'
    }],
    DataCaptureConfig = data_capture_configuration) # This is where the new capture options are applied

print("Endpoint Config Arn: " + create_endpoint_config_response['EndpointConfigArn'])


import time

endpoint_name = 'XGBoost-MovieRec-DataCaptureEndpoint-' + strftime("%Y-%m-%d-%H-%M-%S", gmtime())
print(endpoint_name)
create_endpoint_response = sm_client.create_endpoint(
    EndpointName=endpoint_name,
    EndpointConfigName=endpoint_config_name)
print(create_endpoint_response['EndpointArn'])

resp = sm_client.describe_endpoint(EndpointName=endpoint_name)
status = resp['EndpointStatus']
print("Status: " + status)

while status=='Creating':
    time.sleep(60)
    resp = sm_client.describe_endpoint(EndpointName=endpoint_name)
    status = resp['EndpointStatus']
    print("Status: " + status)

print("Arn: " + resp['EndpointArn'])
print("Status: " + status)


