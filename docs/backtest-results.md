# FaultRay Backtest Accuracy Report

Generated: 2026-03-16 17:56:26
Total Incidents: 18

## Overall Accuracy Summary

| Metric | Value |
|--------|-------|
| Avg Precision | 1.000 |
| Avg Recall | 1.000 |
| Avg F1 Score | 1.000 |
| Avg Severity Accuracy | 0.819 |
| Avg Downtime MAE (min) | 3159.53 |
| Avg Confidence | 0.756 |

## Per-Incident Results

| Incident ID | Component | Precision | Recall | F1 | Sev Acc | DT MAE | Confidence |
|-------------|-----------|-----------|--------|----|---------|--------|------------|
| aws-us-east-1-2021-12 | shared_network | 1.000 | 1.000 | 1.000 | 0.810 | 659.0 | 0.743 |
| aws-s3-2017-02 | shared_network | 1.000 | 1.000 | 1.000 | 0.770 | 299.0 | 0.731 |
| meta-bgp-2021-10 | shared_network | 1.000 | 1.000 | 1.000 | 0.900 | 359.5 | 0.770 |
| cloudflare-2022-06 | physical_infra | 1.000 | 1.000 | 1.000 | 0.700 | 119.0 | 0.710 |
| gcp-2019-06 | shared_network | 1.000 | 1.000 | 1.000 | 0.740 | 264.5 | 0.722 |
| azure-2023-01 | shared_network | 1.000 | 1.000 | 1.000 | 0.770 | 539.0 | 0.731 |
| github-ddos-2018 | shared_network | 1.000 | 1.000 | 1.000 | 0.700 | 19.5 | 0.845 |
| fastly-2021-06 | shared_network | 1.000 | 1.000 | 1.000 | 0.900 | 48.0 | 0.810 |
| crowdstrike-2024-07 | host_os | 1.000 | 1.000 | 1.000 | 0.900 | 1439.5 | 0.770 |
| aws-dynamodb-2015-09 | dynamo_db | 1.000 | 1.000 | 1.000 | 0.980 | 299.5 | 0.794 |
| gcp-lb-2021-11 | shared_network | 1.000 | 1.000 | 1.000 | 0.900 | 149.5 | 0.770 |
| dyn-ddos-2016-10 | shared_network | 1.000 | 1.000 | 1.000 | 0.900 | 479.5 | 0.770 |
| aws-kinesis-2020-11 | shared_network | 1.000 | 1.000 | 1.000 | 0.770 | 599.5 | 0.731 |
| slack-2022-02 | shared_network | 1.000 | 1.000 | 1.000 | 0.700 | 299.0 | 0.710 |
| aws-ebs-2011-04 | shared_network | 1.000 | 1.000 | 1.000 | 0.740 | 2879.5 | 0.722 |
| roblox-2021-10 | shared_network | 1.000 | 1.000 | 1.000 | 0.900 | 4379.5 | 0.770 |
| azure-ad-2021-03 | shared_network | 1.000 | 1.000 | 1.000 | 0.770 | 839.0 | 0.731 |
| ovh-fire-2021-03 | physical_infra | 1.000 | 1.000 | 1.000 | 0.900 | 43199.5 | 0.770 |

## Calibration Recommendations

- **downtime_bias_correction**: 3159.53

## Detailed Results

### aws-us-east-1-2021-12

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, app_server, primary_db, redis, lambda_fn, message_queue, monitoring, container_service
- **Predicted Affected**: app_server, container_service, lambda_fn, message_queue, monitoring, primary_db, redis, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 7.1
- **Actual Downtime**: 660 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, container_service, lambda_fn, message_queue, monitoring, primary_db, redis, shared_network

### aws-s3-2017-02

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, s3_storage, app_server, lambda_fn, message_queue
- **Predicted Affected**: app_server, lambda_fn, message_queue, s3_storage, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 6.7
- **Actual Downtime**: 300 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, lambda_fn, message_queue, s3_storage, shared_network

### meta-bgp-2021-10

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, dns_resolver, cdn
- **Predicted Affected**: cdn, dns_resolver, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 360 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: cdn, dns_resolver, shared_network

### cloudflare-2022-06

- **Failed Component**: physical_infra
- **Actual Affected**: physical_infra, cdn, dns_resolver, api_gw
- **Predicted Affected**: api_gw, cdn, dns_resolver, physical_infra
- **Actual Severity**: major
- **Predicted Severity**: 8.0
- **Actual Downtime**: 120 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: api_gw, cdn, dns_resolver, physical_infra

### gcp-2019-06

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, gce_instance, cloud_sql, gcs_storage
- **Predicted Affected**: cloud_sql, gce_instance, gcs_storage, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 6.4
- **Actual Downtime**: 265 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: cloud_sql, gce_instance, gcs_storage, shared_network

### azure-2023-01

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, azure_vm, azure_sql, azure_blob, azure_lb
- **Predicted Affected**: azure_blob, azure_lb, azure_sql, azure_vm, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 6.7
- **Actual Downtime**: 540 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: azure_blob, azure_lb, azure_sql, azure_vm, shared_network

### github-ddos-2018

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, cdn, main_lb, app_server
- **Predicted Affected**: app_server, cdn, main_lb, shared_network
- **Actual Severity**: major
- **Predicted Severity**: 8.0
- **Actual Downtime**: 20 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, cdn, main_lb, shared_network

### fastly-2021-06

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, cdn, dns_resolver
- **Predicted Affected**: cdn, dns_resolver, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 49 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: cdn, dns_resolver, shared_network

### crowdstrike-2024-07

- **Failed Component**: host_os
- **Actual Affected**: host_os, app_server, azure_vm, gce_instance
- **Predicted Affected**: app_server, azure_vm, gce_instance, host_os
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 1440 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, azure_vm, gce_instance, host_os

### aws-dynamodb-2015-09

- **Failed Component**: dynamo_db
- **Actual Affected**: dynamo_db, app_server, container_service
- **Predicted Affected**: app_server, container_service, dynamo_db
- **Actual Severity**: major
- **Predicted Severity**: 4.8
- **Actual Downtime**: 300 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, container_service, dynamo_db

### gcp-lb-2021-11

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, main_lb, cdn
- **Predicted Affected**: cdn, main_lb, shared_network
- **Actual Severity**: major
- **Predicted Severity**: 6.0
- **Actual Downtime**: 150 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: cdn, main_lb, shared_network

### dyn-ddos-2016-10

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, dns_resolver
- **Predicted Affected**: dns_resolver, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 480 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: dns_resolver, shared_network

### aws-kinesis-2020-11

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, lambda_fn, monitoring, app_server, container_service
- **Predicted Affected**: app_server, container_service, lambda_fn, monitoring, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 6.7
- **Actual Downtime**: 600 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, container_service, lambda_fn, monitoring, shared_network

### slack-2022-02

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, primary_db, app_server, redis, message_queue
- **Predicted Affected**: app_server, message_queue, primary_db, redis, shared_network
- **Actual Severity**: major
- **Predicted Severity**: 8.0
- **Actual Downtime**: 300 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, message_queue, primary_db, redis, shared_network

### aws-ebs-2011-04

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, app_server, primary_db, s3_storage
- **Predicted Affected**: app_server, primary_db, s3_storage, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 6.4
- **Actual Downtime**: 2880 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, primary_db, s3_storage, shared_network

### roblox-2021-10

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, app_server, primary_db, redis, message_queue
- **Predicted Affected**: app_server, message_queue, primary_db, redis, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 4380 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, message_queue, primary_db, redis, shared_network

### azure-ad-2021-03

- **Failed Component**: shared_network
- **Actual Affected**: shared_network, azure_vm, azure_sql, azure_blob, app_server
- **Predicted Affected**: app_server, azure_blob, azure_sql, azure_vm, shared_network
- **Actual Severity**: critical
- **Predicted Severity**: 6.7
- **Actual Downtime**: 840 min
- **Predicted Downtime**: 1.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, azure_blob, azure_sql, azure_vm, shared_network

### ovh-fire-2021-03

- **Failed Component**: physical_infra
- **Actual Affected**: physical_infra, app_server, primary_db, s3_storage
- **Predicted Affected**: app_server, physical_infra, primary_db, s3_storage
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 43200 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, physical_infra, primary_db, s3_storage
