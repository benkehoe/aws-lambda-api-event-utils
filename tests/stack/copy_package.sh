#!/bin/bash

DIR=$(dirname "$(readlink -f "$0")")

cp -r $DIR/../../aws_lambda_api_event_utils $DIR/src/
